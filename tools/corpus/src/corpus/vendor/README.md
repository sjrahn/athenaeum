# Vendored assets

## `single-file.js` (optional)

A browser-bundle build of [SingleFile](https://github.com/gildas-lormeau/single-file)
(MIT-licensed). When present, `corpus.capture` injects it into the
Playwright-controlled page and calls `singlefile.getPageData({...})` to produce a
self-contained snapshot of the rendered DOM with CSS, images, and fonts inlined
as `data:` URIs.

**This file is not committed** (it's ~900 KB and has a documented refresh
procedure). Without it, HTML capture degrades gracefully to a rendered-DOM
snapshot (`page.content()`) — still valid HTML, just without inlined
sub-resources. To enable faithful snapshots, either:

- drop the bundle here as `single-file.js`, or
- point `CORPUS_SINGLEFILE_BUNDLE` at a bundle elsewhere on disk.

The capture loader checks `CORPUS_SINGLEFILE_BUNDLE` first, then this file.

### Refresh procedure

The upstream distribution is a JS module
(`gildas-lormeau/single-file-cli/lib/single-file-bundle.js`) that exports the
bundle as a string constant named `script`. Unwrap that string into a
directly-injectable IIFE so it can be passed to `page.add_script_tag(content=…)`
without a Node runtime:

```sh
cd /tmp
curl -sL -o sf-bundle.js https://raw.githubusercontent.com/gildas-lormeau/single-file-cli/master/lib/single-file-bundle.js
python3 -c '
import re, json
src = open("sf-bundle.js").read()
m = re.match(r"^const script = (\".*?\");(?:\s*const|\s*export)", src, re.DOTALL)
open("single-file.js", "w").write(json.loads(m.group(1)))
'
mv /tmp/single-file.js "$(python3 -c "import corpus, pathlib; print(pathlib.Path(corpus.__file__).parent / 'vendor' / 'single-file.js')")"
```

After refreshing, run a capture against a known URL to confirm the bundle still
works (`corpus capture <url> --no-ingest`).
