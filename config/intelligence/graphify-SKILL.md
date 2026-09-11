---
name: dev-cockpit-graphify
description: Query this project's local Graphify code graph to inspect symbols, relationships, and affected code.
---

Use the `dev-cockpit-graphify` MCP server's `graph_stats`, `query_graph`, `get_node`,
`get_neighbors`, and `shortest_path` tools for the current project's code map.
The graph lives at `.dev-cockpit/intelligence/graph/graphify-out/graph.json`.
Check graph freshness with `dev graph doctor .`; refresh with `dev graph update .`
after source changes. If the MCP server is unavailable, query the same artifact
with `graphify query "symbol or question" --graph
.dev-cockpit/intelligence/graph/graphify-out/graph.json`.

Ground conclusions in the cited source files and current code. The graph contains
local syntax and inferred relationships, not authoritative semantic proof.
Default indexing intentionally uses `--code-only --no-cluster` and makes no model
requests. Do not run semantic extraction, fetch URLs, add global graphs, or install
other agents' hooks/config without the user's request. A graph lookup returning no
matches is a reason to inspect source, not to invent a relationship.
