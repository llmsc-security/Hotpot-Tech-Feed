# Hotpot Tech Feed — User Prompt Log

Every user prompt that built this project, in chronological order. Grouped
into phases for readability; the actual conversation interleaved them.

---

## Phase 1 — Stand up the stack

> docker compose build gateway / bash start.sh

> change the port to 50002, use the nginx to expose only one, change
> OPENAI_API_KEY="111", export OPENAI_BASE_URL="https://api.ai2wj.com/v1/"

> hotpot ingest-now

> Error with model error=ErrorInfo(message='The model `qwen3.6` does not
> exist.' …)

> Qwen/Qwen3.5-397B-A17B

---

## Phase 2 — Faster ingest

> can we speedup this with multiprocess docker compose run --rm backend
> hotpot ingest-now

> workers can be 1/2 cores cpus

---

## Phase 3 — Header chrome

> in the right corner, show the github icon, can link to
> `https://github.com/llmsc-security/Hotpot-Tech-Feed`, also a icon about
> how many corpus we have collected

---

## Phase 4 — Make search smart

> in the search text, it can input the prompt, like how to filter, search,
> it will call the LLM to build the search condition from NLP. you can
> given few shot example as tips.

> the filter in "all topics", "all types" didnot work well

> can sort by date, can have quick group by years: 2026, 2025, …

> can filter by source like "wechat", like "wechat: xxx"

> expect the front ui can search by interacting with llm, to finalize the
> filter+sort condition, then conduct the search

> i dinot like you use the rule or hardcode to service or response the
> user, instead, you have the LLM as agent, llm will understand user and
> interact with you by formula user filter / sort / search condition

> the llm can driven by qwen

---

## Phase 5 — Contribute (v1: single-shot)

> in the right corner top, there is button, "I want to contribute", the
> user can share some source of news, blog, paper url and so on. you can
> accept/clean them and format to yours, if fail, you can warn the user,
> how to submit correct contribute

> hotpot ingest-now

> make sure you have saved the user data

> Contribute a source… `https://projectzero.google/archive.html`
> ⚠ Server error (500). Please try again.

> Ask Hotpot

> openai 2026 blog posts, newest first

> but zero filters:

> feed.ai2wj.com — daily CS digest pwoer by qwen3.5 which a free self-host
> LLM

---

## Phase 6 — Persistence + migration

> make sure the state has saved, e.g migrate to another pc, the server
> need to deploy again, and didnot loss the user data.

> why does "openai 2026 blog posts, newest first" still empty, edit the
> right corner top, "corpus", when click, it list draw card list all the
> source, the main url.

> git push

---

## Phase 7 — Slide deck + repo hygiene

> write the ppt about the system, 3-4 tech and 2 tutorial, then push to
> system

> push to github

> update the .claude folder

> git push

> git push .claude

> only this project related

---

## Phase 8 — Search-input history + consent

> add the tips in search input textbox, about we would record the user
> search input. you can also support to record the text input as history
> list.

> create CLAUD.md file

> "Heads up" should be colored, to highlight user know it. if possible,
> need to alert and wait the user to accept, like the cookie policy,
> accept or reject, because we start collect user info.

> how many user input do we accept and collect?

> git push, but donot include user data

---

## Phase 9 — Contribute (v2: classify → review → commit)

> in the contribute page, when user input a url, there is progress status
> (although user can close this one, and resume it later), contribute page
> can 1. classify the url to category, is category not exist, can proposal
> new category, assume each url can have 2-3 category, you can rank and
> select the first one, but leave all of them to user, user can edit it,
> for example l1,l2,l3, if user select l3, then this url will belong to
> l3. another is how your DB design, explain this one into docs/DB.md,
> given the simple command to access this. assume the password store in
> .env file. make sure this meta "title url content category" exist, at
> final, please output current exist category list.

> 1, update the prompt, the result from Qwen, it always show 1
> classification, expect at least 3 …
> 2, in corpus drawer card, expect show two collection, the category and
> content_type, both give example of top-3

> donot given limitation of category, some url is very wide, i donot know
> "allowed topics", is that limit the qwen proposaled? may be 2+1, 2 is
> allowed topics and last one is open category

> /compact

---

## Phase 10 — Community page (current)

> why does the contribute url will be under review? e.g Pending review (1)
> … if under review, where the admin console to review, may be we can
> support the issue, when we receive the review from "I wanto controbute",
> the system will submit the issue, about the n new URL, and submit the
> PR of this for wairing approve. do you agree ? if not, how can we deal
> with submit url from "contribute"

> 1

> you didnot explain, how can you do with new url contributed

> i want /admin/review, but not the admin level, it is public, can show
> the urls contribute time, the hot trending of it, for example when
> end-users click the news which came from this new contribute url
> click-size, it indicate this new url is more welcome.

> also, /admin/review you can change the url path, it readonly, didnot do
> the approval job. assume the contribute url is accept by auto

> review the system, make sure there is no hardcode, the system persist
> into DB and code. can migrate to another pc.

> write down all the prompts, you can format them, into harness_prompts.md
