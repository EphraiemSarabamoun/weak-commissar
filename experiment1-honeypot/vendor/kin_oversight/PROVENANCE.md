# Provenance of the vendored kin-oversight files

These eight files are copied from the author's kin-oversight repository, which was built during the sprint
(its first commit is dated 2026-11-07 17:03 PST). In the original setup, swarm-board loaded them from a sibling
checkout through `honeypot/swarm_board/kin.py`; in this release that loader reads this folder instead (set
`SWARM_KIN_ROOT` to point it elsewhere). kin-oversight's own recipe re-implements the subject backend of castra, an
earlier, preexisting project of the author's; castra itself is not included or imported.

Source: kin-oversight, commit `16b31ad344ad17386245849e1629a4fe29ddcf7a` (2026-11-08 08:01 PST), copied with
`git archive` (the working tree was not used).

| File | Source sha256 | Last changed in source | Copied unchanged? |
|---|---|---|---|
| `code/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 5273294, 2026-11-07 | yes (empty) |
| `code/subjects.py` | `c06364759f6311ca51ad496143338dc878382141693fded7b774449ff070425c` | 65cf33f, 2026-11-07 | yes |
| `code/probe_check.py` | `d6b1899ccd43fa7469315aed69863793d5072a774d478b28aaeab417d6d1a44b` | 65cf33f, 2026-11-07 | no: release sha256 `0c85ea466e064f2c23841afed9c35719683f2543c764b480bc4952e6034c51ab` |
| `code/analysis/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 5273294, 2026-11-07 | yes (empty) |
| `code/analysis/bootstrap.py` | `0a0ab74c4a289e19c0adceae49b96d25dc1c82e41ad62019bafdccfb138271a3` | 5273294, 2026-11-07 | yes |
| `code/analysis/auroc.py` | `0fbd1a96c878f4f3cb4d90bfed64196a17e26b48af5b7522f90cad19ea409e82` | 5273294, 2026-11-07 | yes |
| `code/analysis/estimands.py` | `b8a089ea9268f1126090a5ab8f04a7ea173ff14c36bbde6cad457564f8794cd4` | 5273294, 2026-11-07 | yes |
| `code/analysis/rows.py` | `482405bddc76c2e799ff0aa32021f3aede150944e255269398a02ea4016012ee` | 5273294, 2026-11-07 | yes |

The one change, to `probe_check.py`, is a privacy redaction: the isolation probe's list of person cues named people
other than the author and local account names. Those entries are now read from the environment variable
`RELEASE_PRIVATE_CUES` (comma-separated) instead of being shipped, so the published list keeps only the author's
name and the persona name. Runs made before the release used the full list. Every changed file in the release, here
and elsewhere, is listed with both hashes in `PATCHES.json` at the repository root.

Only these modules are used: `subjects` (the isolated `claude -p` recipe), `probe_check` (the fail-closed isolation
probe) and `analysis.bootstrap` with its two helpers (the cluster bootstrap). The rest of kin-oversight is not
included.
