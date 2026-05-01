"""Deterministic scoring for the /security projection.

This v1 intentionally uses only local article/source signals. External CVE,
GHSA, KEV, and EPSS mirrors can later feed the same feature keys without
changing the API contract.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.item import Item
from app.models.security_score import SecurityItemScore

SCORE_VERSION = "security-v1"

_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.I)
_GHSA_RE = re.compile(r"\bGHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}\b", re.I)
_CWE_RE = re.compile(r"\bCWE-\d{2,5}\b", re.I)
_URL_RE = re.compile(r"https?://[^\s<>)\"']+", re.I)
_SHA256_RE = re.compile(r"\b[a-f0-9]{64}\b", re.I)
_IP_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
_CVSS_RE = re.compile(
    r"(?:cvss(?:\s*v[0-9.]+)?(?:\s*(?:base)?\s*score)?|base\s+score|severity\s+score)"
    r"[^0-9]{0,18}(10(?:\.0)?|[0-9](?:\.[0-9])?)",
    re.I,
)
_EPSS_RE = re.compile(r"epss[^0-9%]{0,24}(0?\.\d+|[1-9]\d(?:\.\d+)?%?)", re.I)

_PATCH_TERMS = (
    "patch", "patched", "fixed", "fix available", "security update", "update available",
    "upgrade", "升级", "修复", "补丁",
)
_PATCH_VERSION_TERMS = (
    "fixed in", "patched in", "upgrade to", "version", "versions", "版本",
)
_MITIGATION_TERMS = (
    "mitigation", "mitigations", "workaround", "work around", "disable", "block",
    "configuration change", "缓解", "临时措施", "防护", "绕过方案",
)
_DETECTION_TERMS = (
    "detection", "detections", "detect", "yara", "sigma", "snort", "suricata",
    "rule", "rules", "检测", "规则",
)
_IOC_TERMS = (
    "ioc", "iocs", "indicator of compromise", "indicators of compromise",
    "hash", "sha256", "domain", "ip address", "command and control", "c2",
    "失陷指标", "威胁指标",
)
_POC_TERMS = (
    "poc", "proof-of-concept", "proof of concept", "exploit code",
    "public exploit", "github exploit", "weaponized exploit", "复现", "利用代码",
)
_VICTIM_TERMS = (
    "victim", "victims", "targeted", "compromised", "breach", "breached",
    "intrusion", "organizations affected", "customers affected", "遭攻击", "受害",
    "入侵", "攻击事件", "数据泄露",
)
_THREAT_ACTOR_TERMS = (
    "threat actor", "threat group", "apt", "ransomware gang", "lazarus",
    "lockbit", "cl0p", "blackcat", "fin7", "ta505", "攻击者", "黑客组织",
    "勒索软件团伙", "威胁组织",
)
_TIMELINE_TERMS = (
    "timeline", "first observed", "observed on", "disclosed on", "reported on",
    "released on", "since ", "时间线", "披露", "首次发现",
)
_EXPLOITED_TERMS = (
    "exploited in the wild", "active exploitation", "actively exploited",
    "known exploited", "being exploited", "exploitation observed",
    "exploitation has been observed", "attacks exploiting", "在野利用",
    "已被利用", "正被利用", "遭利用",
)
_VENDOR_CONFIRMED_TERMS = (
    "confirmed exploitation", "confirmed that attackers", "vendor confirmed",
    "the company confirmed", "confirmed active exploitation", "厂商确认",
)
_CREDIBLE_EXPLOIT_TERMS = (
    "researchers observed", "observed attacks", "attack campaign",
    "used by attackers", "used by threat actors", "campaign exploiting",
    "攻击活动", "攻击链",
)
_THEORETICAL_TERMS = (
    "vulnerability", "vulnerabilities", "security flaw", "bug", "弱点", "漏洞",
)
_GENERIC_SECURITY_TERMS = (
    "best practices", "top trends", "ultimate guide", "what you need to know",
    "why it matters", "security posture", "cyber resilience",
    "digital transformation", "modern security teams", "ciso guide",
    "checklist", "zero trust journey", "最佳实践", "趋势", "指南",
)
_PROMO_CTA_TERMS = (
    "book a demo", "request a demo", "contact sales", "download the whitepaper",
    "download the report", "register for webinar", "join our webinar",
    "talk to an expert", "free trial", "立即试用", "预约演示", "联系我们",
)
_PITCH_TERMS = (
    "our platform", "our solution", "our customers", "industry-leading",
    "next-generation", "ai-powered platform", "unified platform",
    "single pane of glass", "award-winning", "领先平台", "解决方案",
)
_COMMON_PRODUCT_TERMS = (
    "windows", "linux", "apache", "nginx", "openssl", "chrome", "android",
    "ios", "wordpress", "kubernetes", "docker", "jenkins", "gitlab",
    "confluence", "jira", "exchange", "sharepoint", "fortinet", "palo alto",
    "cisco", "ivanti", "citrix", "vmware", "oracle", "sap", "microsoft",
    "github", "npm", "pypi", "maven", "go module", "rust crate", "router",
    "vpn", "firewall", "appliance",
)
_CRITICAL_ENTERPRISE_TERMS = (
    "vpn", "firewall", "router", "appliance", "identity", "active directory",
    "exchange", "sharepoint", "confluence", "jira", "citrix", "ivanti",
    "fortinet", "palo alto", "cisco", "vmware", "kubernetes", "cloud",
)
_INTERNET_FACING_TERMS = (
    "internet-facing", "publicly exposed", "remote unauthenticated",
    "remote code execution", "rce", "network exploitable", "web server",
    "公网", "远程代码执行", "无需认证",
)
_LOW_COMPLEXITY_TERMS = (
    "low attack complexity", "unauthenticated", "no user interaction",
    "remote code execution", "rce", "pre-auth", "无需认证", "无需用户交互",
)
_MEDIUM_COMPLEXITY_TERMS = (
    "user interaction", "requires authentication", "authenticated attacker",
)
_VENDOR_ADVISORY_TERMS = (
    "security advisory", "vendor advisory", "product security advisory",
    "advisory", "公告", "安全通告",
)
_PRIMARY_RESEARCH_SOURCES = (
    "project zero", "google security", "mandiant", "talos", "unit 42",
    "unit42", "trail of bits", "portswigger", "rapid7", "watchtowr",
    "horizon3", "wiz", "qualys", "elastic security", "sentinelone",
    "microsoft threat intelligence", "trend micro", "kaspersky", "eset",
    "sophos", "crowdstrike", "secureworks", "zscaler", "akamai",
)
_CREDIBLE_MEDIA_SOURCES = (
    "bleepingcomputer", "securityweek", "the hacker news", "dark reading",
    "krebs", "the record", "sc magazine", "bankinfosecurity", "cybernews",
    "freebuf", "doonsec", "anquanke",
)


def score_security_item(item: Item) -> dict[str, Any]:
    text = _item_text(item)
    text_l = text.lower()
    source_blob = _source_blob(item)
    source_blob_l = source_blob.lower()
    event_time = _ensure_tz(item.published_at or item.fetched_at)

    cves = _unique(m.group(0).upper() for m in _CVE_RE.finditer(text))
    ghsas = _unique(m.group(0).upper() for m in _GHSA_RE.finditer(text))
    cwes = _unique(m.group(0).upper() for m in _CWE_RE.finditer(text))

    has_patch = _contains_any(text_l, _PATCH_TERMS)
    has_patch_version = has_patch and (_contains_any(text_l, _PATCH_VERSION_TERMS) or _has_version_range(text))
    has_mitigation = _contains_any(text_l, _MITIGATION_TERMS)
    has_detection = _contains_any(text_l, _DETECTION_TERMS)
    has_ioc = _contains_any(text_l, _IOC_TERMS) or bool(_SHA256_RE.search(text_l) or _IP_RE.search(text_l))
    has_poc = _contains_any(text_l, _POC_TERMS)
    has_victim = _contains_any(text_l, _VICTIM_TERMS)
    has_threat_actor = _contains_any(text_l, _THREAT_ACTOR_TERMS)
    has_timeline = _contains_any(text_l, _TIMELINE_TERMS)
    has_affected_version = _has_version_range(text) or "affected version" in text_l or "affected versions" in text_l
    has_product = _contains_any(text_l, _COMMON_PRODUCT_TERMS) or bool(item.lab or item.venue)

    cvelist_match = bool(cves and _contains_any(source_blob_l, ("cveproject", "cve.org", "nvd.nist.gov", "nvd")))
    github_advisory_match = bool(
        ghsas and (
            "github advisory" in text_l
            or "github.com/advisories" in text_l
            or "github advisory" in source_blob_l
            or "github.com/advisories" in source_blob_l
        )
    )
    cisa_kev_match = bool(
        cves
        and (
            ("cisa" in text_l and ("kev" in text_l or "known exploited" in text_l))
            or ("cisa.gov" in source_blob_l and "known exploited" in text_l)
        )
    )
    vendor_advisory_match = bool(
        _contains_any(text_l, _VENDOR_ADVISORY_TERMS)
        or _contains_any(source_blob_l, _VENDOR_ADVISORY_TERMS)
        or ("msrc" in source_blob_l)
    )
    primary_research_match = _contains_any(source_blob_l, _PRIMARY_RESEARCH_SOURCES)
    credible_media_match = _contains_any(source_blob_l, _CREDIBLE_MEDIA_SOURCES)

    attack_status = _attack_status(
        text_l,
        cisa_kev_match=cisa_kev_match,
        has_poc=has_poc,
        vendor_advisory_match=vendor_advisory_match,
        credible_media_match=credible_media_match,
        primary_research_match=primary_research_match,
        has_vulnerability=bool(cves or ghsas or _contains_any(text_l, _THEORETICAL_TERMS)),
    )

    source_link_count = len({u.rstrip(".,);]") for u in _URL_RE.findall(text)})
    generic_count = _count_terms(text_l, _GENERIC_SECURITY_TERMS)
    promo_cta_count = _count_terms(text_l, _PROMO_CTA_TERMS)
    product_pitch_count = _count_terms(text_l, _PITCH_TERMS)
    cvss_score = _extract_cvss(text)
    epss_percentile = _extract_epss_percentile(text)

    relevance = _clamp(
        (0.35 if cves else 0.0)
        + (0.25 if ghsas else 0.0)
        + (0.30 if cvelist_match else 0.0)
        + (0.30 if github_advisory_match else 0.0)
        + (0.50 if cisa_kev_match else 0.0)
        + (0.20 if has_victim else 0.0)
        + (0.15 if has_threat_actor else 0.0)
        + (0.15 if has_ioc else 0.0)
        + (0.10 if has_timeline else 0.0)
        + (0.15 if has_patch else 0.0)
        + (0.10 if has_mitigation else 0.0)
        + (0.10 if has_affected_version else 0.0)
    )

    evidence = _clamp(
        (0.25 if cvelist_match else 0.15 if cves else 0.0)
        + (0.20 if github_advisory_match else 0.12 if ghsas else 0.0)
        + (0.30 if cisa_kev_match else 0.0)
        + (0.08 if has_poc else 0.0)
        + (0.10 if has_victim else 0.0)
        + (0.08 if has_threat_actor else 0.0)
        + (0.06 if has_timeline else 0.0)
        + (0.08 if has_affected_version else 0.0)
        + (0.08 if has_patch else 0.0)
        + (0.05 if has_mitigation else 0.0)
        + (0.08 if has_ioc else 0.0)
        + (0.08 if vendor_advisory_match else 0.0)
        + (0.08 if primary_research_match else 0.0)
        + (0.04 if credible_media_match else 0.0)
        + (0.06 if source_link_count >= 3 else 0.03 if source_link_count >= 1 else 0.0)
    )

    exploitation = {
        "cisa_kev": 1.0,
        "confirmed_in_the_wild": 0.90,
        "vendor_confirmed_exploitation": 0.85,
        "credible_report_claims_exploitation": 0.70,
        "public_poc_available": 0.45,
        "theoretical_only": 0.20,
        "unknown": 0.0,
    }[attack_status]

    quality = _clamp(
        (0.12 if cves else 0.0)
        + (0.10 if ghsas else 0.0)
        + (0.08 if has_product else 0.0)
        + (0.10 if has_affected_version else 0.0)
        + (0.12 if has_patch else 0.0)
        + (0.08 if has_mitigation else 0.0)
        + (0.10 if has_ioc else 0.0)
        + (0.08 if has_victim else 0.0)
        + (0.08 if has_threat_actor else 0.0)
        + (0.06 if has_timeline else 0.0)
        + (0.10 if source_link_count >= 3 else 0.05 if source_link_count >= 1 else 0.0)
        + (0.08 if has_poc else 0.0)
        - min(0.18, generic_count * 0.03)
    )

    impact = _clamp(
        (0.25 if cvss_score and cvss_score >= 9.0 else 0.15 if cvss_score and cvss_score >= 7.0 else 0.08 if cvss_score and cvss_score >= 5.0 else 0.0)
        + (0.30 if epss_percentile and epss_percentile >= 0.95 else 0.20 if epss_percentile and epss_percentile >= 0.80 else 0.10 if epss_percentile and epss_percentile >= 0.50 else 0.0)
        + (0.20 if _contains_any(text_l, _CRITICAL_ENTERPRISE_TERMS) else 0.0)
        + (0.12 if _contains_any(text_l, _COMMON_PRODUCT_TERMS) else 0.0)
        + (0.15 if _contains_any(text_l, _INTERNET_FACING_TERMS) else 0.0)
        + (0.10 if _contains_any(text_l, _LOW_COMPLEXITY_TERMS) else 0.05 if _contains_any(text_l, _MEDIUM_COMPLEXITY_TERMS) else 0.0)
    )

    actionability = _clamp(
        (0.22 if has_patch else 0.0)
        + (0.18 if has_patch_version else 0.0)
        + (0.16 if has_mitigation else 0.0)
        + (0.14 if has_detection else 0.0)
        + (0.12 if has_ioc else 0.0)
        + (0.10 if has_affected_version else 0.0)
        + (0.08 if "workaround" in text_l or "work around" in text_l or "临时措施" in text_l else 0.0)
        + (0.06 if "configuration" in text_l or "configure" in text_l or "配置" in text_l else 0.0)
    )

    soft_article = _clamp(
        min(0.30, promo_cta_count * 0.10)
        + min(0.25, product_pitch_count * 0.08)
        + min(0.24, generic_count * 0.04)
        + (0.15 if not cves and not ghsas else 0.0)
        + (0.15 if not has_patch and not has_mitigation and not has_ioc else 0.0)
        + (0.10 if not has_victim and not has_threat_actor and not has_affected_version else 0.0)
        + (0.10 if source_link_count == 0 else 0.0)
    )

    freshness = _freshness_score(event_time)
    source_authority = _source_authority_score(
        source_blob_l,
        source_trust=item.source.trust_score if item.source else None,
        evidence_score=evidence,
        soft_article_score=soft_article,
        cisa_kev_match=cisa_kev_match,
        cvelist_match=cvelist_match,
        github_advisory_match=github_advisory_match,
        vendor_advisory_match=vendor_advisory_match,
        primary_research_match=primary_research_match,
        credible_media_match=credible_media_match,
    )
    source_types = _source_types(
        cves=cves,
        ghsas=ghsas,
        cisa_kev_match=cisa_kev_match,
        github_advisory_match=github_advisory_match,
        cvelist_match=cvelist_match,
        vendor_advisory_match=vendor_advisory_match,
        primary_research_match=primary_research_match,
        credible_media_match=credible_media_match,
        exposure_count=item.exposure_count or 1,
    )
    corroboration = _corroboration_score(len(source_types))

    final_score = _clamp(
        0.30 * evidence
        + 0.24 * exploitation
        + 0.14 * quality
        + 0.10 * impact
        + 0.08 * actionability
        + 0.06 * source_authority
        + 0.05 * corroboration
        + 0.03 * freshness
        - 0.22 * soft_article
    )
    click_score = min((item.click_count or 0) / 10.0, 1.0)
    repeat_score = min(max((item.exposure_count or 1) - 1, 0) / 8.0, 1.0)
    hot_score = _clamp(
        0.80 * final_score
        + 0.08 * freshness
        + 0.07 * corroboration
        + 0.03 * click_score
        + 0.02 * repeat_score
    )

    soft_reject = (
        soft_article >= 0.75
        or (soft_article >= 0.55 and evidence < 0.45)
        or (
            not cves
            and not ghsas
            and not has_victim
            and not has_threat_actor
            and not has_patch
            and not has_ioc
            and soft_article >= 0.45
        )
    )
    confirmed_exploitation = attack_status in {"cisa_kev", "confirmed_in_the_wild", "vendor_confirmed_exploitation"}
    accepted = (
        relevance >= 0.40
        and (evidence >= 0.35 or cisa_kev_match or confirmed_exploitation)
        and not soft_reject
        and final_score >= 0.30
    )
    reject_reason = None
    if not accepted:
        if relevance < 0.40:
            reject_reason = "low_security_relevance"
        elif soft_reject:
            reject_reason = "soft_article"
        elif evidence < 0.35 and not cisa_kev_match and not confirmed_exploitation:
            reject_reason = "weak_evidence"
        elif final_score < 0.30:
            reject_reason = "low_final_score"
        else:
            reject_reason = "not_accepted"

    features = {
        "mentioned_cves": cves,
        "mentioned_ghsas": ghsas,
        "mentioned_cwes": cwes,
        "cvelist_match": cvelist_match,
        "github_advisory_match": github_advisory_match,
        "cisa_kev_match": cisa_kev_match,
        "epss_percentile": epss_percentile,
        "vendor_advisory_match": vendor_advisory_match,
        "primary_research_match": primary_research_match,
        "credible_media_match": credible_media_match,
        "attack_status": attack_status,
        "has_victim": has_victim,
        "has_threat_actor": has_threat_actor,
        "has_timeline": has_timeline,
        "has_ioc": has_ioc,
        "has_poc": has_poc,
        "has_patch": has_patch,
        "has_patch_version": has_patch_version,
        "has_mitigation": has_mitigation,
        "has_detection": has_detection,
        "has_affected_version": has_affected_version,
        "cvss_score": cvss_score,
        "source_links_count": source_link_count,
        "promotional_cta_count": promo_cta_count,
        "product_pitch_count": product_pitch_count,
        "generic_security_phrase_count": generic_count,
        "source_types": source_types,
    }

    return {
        "accepted": accepted,
        "reject_reason": reject_reason,
        "score_version": SCORE_VERSION,
        "group_key": _group_key(item, cves=cves, ghsas=ghsas),
        "representative_item_id": item.id,
        "section": _section(features, evidence_score=evidence, content_quality_score=quality),
        "event_time": event_time,
        "security_relevance_score": round(relevance, 4),
        "evidence_score": round(evidence, 4),
        "exploitation_score": round(exploitation, 4),
        "content_quality_score": round(quality, 4),
        "impact_score": round(impact, 4),
        "actionability_score": round(actionability, 4),
        "source_authority_score": round(source_authority, 4),
        "freshness_score": round(freshness, 4),
        "corroboration_score": round(corroboration, 4),
        "soft_article_score": round(soft_article, 4),
        "final_security_score": round(final_score, 4),
        "security_hot_score": round(hot_score, 4),
        "badges": _badges(features, cvss_score=cvss_score),
        "why_ranked": _why_ranked(item, features, evidence, exploitation, actionability, source_authority),
        "source_chain": source_types,
        "features": features,
    }


def upsert_security_score(db: Session, item: Item) -> SecurityItemScore:
    payload = score_security_item(item)
    row = db.get(SecurityItemScore, item.id)
    if row is None:
        row = SecurityItemScore(item_id=item.id)
        db.add(row)
    for key, value in payload.items():
        setattr(row, key, value)
    row.computed_at = datetime.now(timezone.utc)
    return row


def score_security_items(
    db: Session,
    *,
    limit: int | None = 1000,
    missing_only: bool = False,
    recent_days: int | None = None,
) -> dict[str, Any]:
    stmt = (
        select(Item)
        .options(selectinload(Item.tags), selectinload(Item.source))
        .where(Item.is_canonical.is_(True))
        .order_by(Item.fetched_at.desc())
    )
    if missing_only:
        stmt = stmt.outerjoin(SecurityItemScore, SecurityItemScore.item_id == Item.id).where(
            SecurityItemScore.item_id.is_(None)
        )
    if recent_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=recent_days)
        stmt = stmt.where((Item.published_at >= cutoff) | (Item.fetched_at >= cutoff))
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = db.execute(stmt).scalars().unique().all()
    counts = {"processed": 0, "accepted": 0, "rejected": 0, "errors": 0, "score_version": SCORE_VERSION}
    for item in rows:
        try:
            score = upsert_security_score(db, item)
            counts["processed"] += 1
            if score.accepted:
                counts["accepted"] += 1
            else:
                counts["rejected"] += 1
        except Exception:
            counts["errors"] += 1
    return counts


def _item_text(item: Item) -> str:
    tags = " ".join(t.tag for t in getattr(item, "tags", []) or [])
    source_name = item.source.name if item.source else ""
    return "\n".join(
        part
        for part in (
            item.title,
            item.summary or "",
            item.excerpt or "",
            item.lab or "",
            item.venue or "",
            source_name,
            tags,
        )
        if part
    )


def _source_blob(item: Item) -> str:
    if not item.source:
        return ""
    return " ".join(
        str(x)
        for x in (
            item.source.name,
            item.source.url,
            item.source.lab or "",
            (item.source.extra or {}).get("lineage", ""),
        )
        if x
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _count_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(text.count(term) for term in terms)


def _unique(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _has_version_range(text: str) -> bool:
    return bool(
        re.search(r"\b(?:before|prior to|through|<=|<|from)\s+v?\d+(?:\.\d+){1,3}\b", text, re.I)
        or re.search(r"\bv?\d+(?:\.\d+){1,3}\s+(?:and earlier|or earlier|及以前|之前)\b", text, re.I)
    )


def _extract_cvss(text: str) -> float | None:
    scores: list[float] = []
    for match in _CVSS_RE.finditer(text):
        try:
            score = float(match.group(1))
        except ValueError:
            continue
        if 0.0 <= score <= 10.0:
            scores.append(score)
    return max(scores) if scores else None


def _extract_epss_percentile(text: str) -> float | None:
    vals: list[float] = []
    for match in _EPSS_RE.finditer(text):
        raw = match.group(1)
        try:
            if raw.endswith("%"):
                val = float(raw[:-1]) / 100.0
            else:
                val = float(raw)
                if val > 1.0:
                    val = val / 100.0
        except ValueError:
            continue
        if 0.0 <= val <= 1.0:
            vals.append(val)
    return max(vals) if vals else None


def _attack_status(
    text_l: str,
    *,
    cisa_kev_match: bool,
    has_poc: bool,
    vendor_advisory_match: bool,
    credible_media_match: bool,
    primary_research_match: bool,
    has_vulnerability: bool,
) -> str:
    if cisa_kev_match:
        return "cisa_kev"
    if _contains_any(text_l, _EXPLOITED_TERMS):
        return "confirmed_in_the_wild"
    if vendor_advisory_match and _contains_any(text_l, _VENDOR_CONFIRMED_TERMS):
        return "vendor_confirmed_exploitation"
    if (credible_media_match or primary_research_match) and _contains_any(text_l, _CREDIBLE_EXPLOIT_TERMS):
        return "credible_report_claims_exploitation"
    if has_poc:
        return "public_poc_available"
    if has_vulnerability:
        return "theoretical_only"
    return "unknown"


def _source_authority_score(
    source_blob_l: str,
    *,
    source_trust: float | None,
    evidence_score: float,
    soft_article_score: float,
    cisa_kev_match: bool,
    cvelist_match: bool,
    github_advisory_match: bool,
    vendor_advisory_match: bool,
    primary_research_match: bool,
    credible_media_match: bool,
) -> float:
    trust = max(0.0, min(float(source_trust if source_trust is not None else 0.5), 1.0))
    score = 0.15 + trust * 0.45
    if cisa_kev_match or "cisa.gov" in source_blob_l:
        score = max(score, 1.0)
    if cvelist_match:
        score = max(score, 0.95)
    if vendor_advisory_match:
        score = max(score, 0.90)
    if github_advisory_match:
        score = max(score, 0.85)
    if primary_research_match:
        score = max(score, 0.80)
    if credible_media_match:
        score = max(score, 0.65)
    if vendor_advisory_match and evidence_score >= 0.70:
        score = max(score, 0.75)
    if vendor_advisory_match and soft_article_score >= 0.55 and evidence_score < 0.45:
        score = min(score, 0.20)
    return _clamp(score)


def _source_types(
    *,
    cves: list[str],
    ghsas: list[str],
    cisa_kev_match: bool,
    github_advisory_match: bool,
    cvelist_match: bool,
    vendor_advisory_match: bool,
    primary_research_match: bool,
    credible_media_match: bool,
    exposure_count: int,
) -> list[str]:
    out: list[str] = []
    if cvelist_match:
        out.append("cvelistV5")
    elif cves:
        out.append("CVE identifier")
    if github_advisory_match:
        out.append("GitHub Advisory")
    elif ghsas:
        out.append("GHSA identifier")
    if cisa_kev_match:
        out.append("CISA KEV")
    if vendor_advisory_match:
        out.append("vendor advisory")
    if primary_research_match:
        out.append("primary research")
    if credible_media_match:
        out.append("credible media")
    if exposure_count > 1:
        out.append("repeat exposure")
    return out


def _corroboration_score(n: int) -> float:
    if n >= 4:
        return 1.0
    if n == 3:
        return 0.80
    if n == 2:
        return 0.60
    if n == 1:
        return 0.30
    return 0.0


def _freshness_score(ts: datetime | None) -> float:
    if ts is None:
        return 0.05
    now = datetime.now(timezone.utc)
    ts = _ensure_tz(ts)
    age = max((now - ts).total_seconds(), 0.0)
    if age <= 86400:
        return 1.0
    if age <= 3 * 86400:
        return 0.80
    if age <= 7 * 86400:
        return 0.55
    if age <= 30 * 86400:
        return 0.25
    return 0.05


def _group_key(item: Item, *, cves: list[str], ghsas: list[str]) -> str:
    if cves:
        return f"cve:{cves[0]}"
    if ghsas:
        return f"ghsa:{ghsas[0]}"
    if item.dedup_group_id:
        return f"dedup:{item.dedup_group_id}"
    title = re.sub(r"https?://\S+", " ", item.title.lower())
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", title)
    title = re.sub(r"\b(?:critical|high|medium|low|vulnerability|flaw|bug|security|alert|warning)\b", " ", title)
    slug = re.sub(r"\s+", " ", title).strip()[:120]
    return f"story:{slug or str(item.id)}"


def _section(features: dict[str, Any], *, evidence_score: float, content_quality_score: float) -> str:
    attack_status = features["attack_status"]
    if features["cisa_kev_match"] or attack_status in {"confirmed_in_the_wild", "vendor_confirmed_exploitation"}:
        return "exploited_now"
    if features["mentioned_cves"] and evidence_score >= 0.45 and (
        (features["cvss_score"] or 0) >= 8.0
        or (features["epss_percentile"] or 0) >= 0.80
        or features["github_advisory_match"]
    ):
        return "new_important_cves"
    if (
        features["has_victim"]
        or features["has_threat_actor"]
        or features["has_ioc"]
        or features["has_timeline"]
    ) and evidence_score >= 0.50:
        return "real_attack_cases"
    if (
        features["has_poc"]
        or features["has_ioc"]
        or features["has_affected_version"]
        or features["has_mitigation"]
    ) and content_quality_score >= 0.55:
        return "technical_analysis"
    if features["vendor_advisory_match"] and (
        features["has_patch"] or features["has_mitigation"] or features["has_affected_version"]
    ):
        return "vendor_advisories"
    if features["github_advisory_match"] or features["mentioned_ghsas"]:
        return "oss_package_vulnerabilities"
    return "all"


def _badges(features: dict[str, Any], *, cvss_score: float | None) -> list[str]:
    badges: list[str] = []
    if features["mentioned_cves"]:
        badges.append(features["mentioned_cves"][0])
    if features["mentioned_ghsas"]:
        badges.append(features["mentioned_ghsas"][0])
    if features["cisa_kev_match"]:
        badges.append("CISA KEV")
    if features["attack_status"] in {"confirmed_in_the_wild", "vendor_confirmed_exploitation"}:
        badges.append("Exploited")
    if features["has_patch"]:
        badges.append("Patch")
    if features["has_mitigation"]:
        badges.append("Mitigation")
    if features["has_ioc"]:
        badges.append("IoCs")
    if features["has_poc"]:
        badges.append("PoC")
    if cvss_score and cvss_score >= 8.0:
        badges.append(f"CVSS {cvss_score:g}")
    if features["has_threat_actor"]:
        badges.append("Threat actor")
    if features["has_victim"]:
        badges.append("Victim")
    return badges[:8]


def _why_ranked(
    item: Item,
    features: dict[str, Any],
    evidence_score: float,
    exploitation_score: float,
    actionability_score: float,
    source_authority_score: float,
) -> list[str]:
    reasons: list[str] = []
    if features["cisa_kev_match"]:
        reasons.append("CISA KEV or known-exploited signal")
    elif exploitation_score >= 0.85:
        reasons.append("confirmed exploitation signal")
    elif exploitation_score >= 0.70:
        reasons.append("credible exploitation report")
    elif features["has_poc"]:
        reasons.append("public PoC signal")
    if features["mentioned_cves"]:
        reasons.append(f"{features['mentioned_cves'][0]} mentioned")
    elif features["mentioned_ghsas"]:
        reasons.append(f"{features['mentioned_ghsas'][0]} mentioned")
    if evidence_score >= 0.60:
        reasons.append("strong evidence density")
    elif evidence_score >= 0.45:
        reasons.append("acceptable evidence density")
    if actionability_score >= 0.50:
        reasons.append("patch, mitigation, detection, or IoC detail")
    if source_authority_score >= 0.75:
        reasons.append("authoritative security source")
    if (item.exposure_count or 1) > 1:
        reasons.append(f"{item.exposure_count} repeated exposures")
    return reasons[:6]


def _ensure_tz(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))
