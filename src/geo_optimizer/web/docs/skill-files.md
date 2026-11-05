# Skill Files

Skill Files are a client handoff bundle for AI tools.

They give Cursor, Claude, Codex, or another AI assistant the GEOSITION operating context it needs to help with implementation instead of guessing from a screenshot or a vague audit summary.

## What gets copied

The bundle points the AI tool to the important GEOSITION surfaces:

- audit and scoring logic
- crawler, robots.txt, `llms.txt`, schema, and page-audit flows
- CLI and MCP entry points
- platform workflow files
- documentation the AI should keep open
- a suggested prompt for using the evidence correctly

It is not a secret key, not customer private data, and not a replacement for the dashboard. It is structured context for doing the work faster and with fewer mistakes.

## Why clients care

Agencies and consultants can use Skill Files to turn a GEOSITION audit into implementation work:

1. Verify a client domain.
2. Run a site audit, page audit, and benchmark.
3. Copy Skill Files.
4. Paste them into an AI coding tool.
5. Ask the tool to apply the recommendations using the real GEOSITION workflow.
6. Re-run the audit and benchmark to prove before/after movement.

That makes the dashboard useful beyond reporting. It becomes the evidence layer for fixing the site.

## Free vs paid access

Free workspaces include the core Skill Files bundle for manual work:

- copy the context
- paste it into an AI tool
- use it while fixing pages
- re-run audits manually

Paid access is for recurring GEOSITION AI automation:

- extension-ready skills
- scheduled CLI runs
- recurring page and benchmark collection
- weekly before/after client proof reports
- ongoing monitoring across client domains

In plain English: free helps a user do one audit-to-fix loop. Paid helps an agency run that loop every week for clients.

## Recommended prompt

After copying Skill Files, paste them into your AI tool and start with:

```text
Use this GEOSITION Skill Files bundle as source-of-truth context.
Help me improve this verified domain by reading audit evidence,
prioritizing the highest-impact fixes, changing the right files,
and telling me what to re-run to prove the before/after delta.
```

## Good use cases

- Fixing `robots.txt`, `llms.txt`, schema, metadata, headings, and crawler access
- Turning page-audit recommendations into concrete code changes
- Preparing weekly client updates with before/after evidence
- Helping an agency operator keep the GEOSITION workflow consistent across clients

## What not to do

Do not paste API keys, private customer data, or database credentials into external AI tools. Skill Files are meant to provide code paths and workflow context, not secrets.
