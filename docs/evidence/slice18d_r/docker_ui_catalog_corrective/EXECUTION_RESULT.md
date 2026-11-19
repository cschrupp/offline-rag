# 18D-R Docker UI Catalog Corrective — Execution Record

## Disposition

```yaml
result: PARTIAL
branch: corrective/18d-r-docker-ui-catalog
remote_branch: PUSHED
corrective_commit: c76d487b38a599c474cdb3a4470600d24d2876be
parent: ef606f667ad13a4730ef04fef648ff1f800d8652
changed_implementation_paths:
  - deploy/Dockerfile
ui_build: PASS
ui_builder_docker_build: UNAVAILABLE_DOCKER_SOCKET_PERMISSION_DENIED
full_cpu_image_build: NOT_RUN
push: SUCCESS
promotion: NOT_AUTHORIZED
```

## Defect reproduction and correction

At the exact authorized base, `ui/src/features/indicators/catalog.ts` imports
`../../../../eval/presentation/indicator_catalog_v1.json`. The file exists at
that repository path, but the Docker `ui-builder` stage copied only `ui/`
before running `npm run build`. The required repo-level JSON was therefore
outside the build context available to TypeScript.

The only implementation change adds the precise catalog file to the UI
builder stage before the build. The authoritative source and repo-relative
import remain unchanged; the whole `eval/` directory is not copied.

## Validation

- `git diff --check`: PASS.
- `cd ui && npm run build`: PASS; 2,098 modules transformed and Vite build
  completed. This ran in the isolated checkout of the exact base. Its
  `node_modules` was linked to the existing local UI dependency installation;
  `ui/package.json` and `ui/package-lock.json` hashes matched the exact base.
- Required Docker UI-builder command was attempted:
  `docker build --target ui-builder -f deploy/Dockerfile -t seneca-18dr-ui-buildcheck .`
  Docker could not connect to `/var/run/docker.sock` (`permission denied`).
  Therefore Docker UI-builder and full-image provenance qualification are
  unavailable in this execution environment. The npm build is not represented
  as Docker qualification.
- Full CPU image build, image labels/size inspection, and full-image provenance
  test were not run because Docker daemon access was unavailable.

## Remote branch

GitHub branch search found no existing
`corrective/18d-r-docker-ui-catalog` branch. The connected GitHub integration's
branch-creation API returned HTTP 403 (`Resource not accessible by
integration`). After network push authorization was granted, the branch was
created by a normal non-force `git push`; the corrective and evidence commits
were pushed to that branch. `main` was not changed.

## Scope integrity

The implementation commit changes only `deploy/Dockerfile`; it changes no
catalog definitions or values, scientific/evaluation evidence, model/runtime
configuration, or application behavior. The H1/H2 review model remains absent
from repository configuration. Historical evidence was not rewritten.

## Exact authorization prompt

See the verbatim attachment copy in `AUTHORIZATION_PROMPT.txt`.

## Exact final execution response

> **Disposition: PARTIAL.** The catalog-copy corrective is committed at
> `c76d487b38a599c474cdb3a4470600d24d2876be`, parent
> `ef606f667ad13a4730ef04fef648ff1f800d8652`, on
> `corrective/18d-r-docker-ui-catalog`. The only implementation change is in
> `deploy/Dockerfile`: it copies only
> `eval/presentation/indicator_catalog_v1.json` into the UI builder before
> `npm run build`.
>
> `git diff --check` and `cd ui && npm run build` passed. The frontend build
> used the existing dependency installation after confirming the package and
> lockfile match the authorized base. The Docker UI-builder command was
> attempted but unavailable because access to `/var/run/docker.sock` was denied;
> the full CPU-image build and image-provenance inspection were not run. No
> unrelated application or scientific behavior changed.
>
> The corrective and evidence commits are pushed to
> `corrective/18d-r-docker-ui-catalog`. GitHub integration branch creation had
> returned HTTP 403, so the authorized normal push path was used. No promotion,
> H1/H2 acceptance, public release, or Milestone 7 closeout is claimed.
