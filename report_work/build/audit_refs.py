"""Cross-reference audit of the built report: figures, tables, sections, appendix parts, citations, links."""
import re, sys
src = open(sys.argv[1], encoding='utf-8').read()
body = re.sub(r'^---\n.*?\n---\n', '', src, flags=re.S)
main, rest = body.split('\n## References\n', 1)
refs_txt, app = rest.split('\n## Appendix A', 1)
app = '## Appendix A' + app
figs = re.findall(r'!\[Figure ([A-Z]?\d+)\.', body)
tabs = re.findall(r'^Table ([A-Z]?\d+)\.', body, re.M)
secs = re.findall(r'^##+ (\d(?:\.\d)?)\.? ', body, re.M)
apps = re.findall(r'^## Appendix ([A-Z])\.', body, re.M)
parts = re.findall(r'^### ([A-Z]\.\d+)\b', body, re.M)
print('figures:', figs); print('tables:', tabs); print('sections:', secs); print('appendices:', apps); print('appendix parts:', parts)
text = re.sub(r'!\[Figure [A-Z]?\d+\.', '![', body)            # drop the definitions themselves
text = re.sub(r'^Table [A-Z]?\d+\.', '', text, flags=re.M)
bad = []
used_f = set(re.findall(r'Figures? ([A-Z]?\d+)', text)) | set(re.findall(r'Figures? [A-Z]?\d+(?:, [A-Z]?\d+)* and ([A-Z]?\d+)', text))
used_t = set(re.findall(r'Tables? ([A-Z]?\d+)', text)) | set(re.findall(r'Tables? [A-Z]?\d+ and ([A-Z]?\d+)', text))
for f in sorted(used_f):
    if f not in figs: bad.append('figure referenced but not defined: ' + f)
for t in sorted(used_t):
    if t not in tabs: bad.append('table referenced but not defined: ' + t)
for f in figs:
    if f not in used_f: bad.append('figure never mentioned: ' + f)
for t in tabs:
    if t not in used_t: bad.append('table never mentioned: ' + t)
for a in set(re.findall(r'Appendix ([A-Z])\b', text)):
    if a not in apps: bad.append('appendix referenced but missing: ' + a)
for p in set(re.findall(r'\b([A-J]\.\d+)\b', re.sub(r'^### .*$', '', text, flags=re.M))):
    if p not in parts: bad.append('appendix part referenced but missing: ' + p)
for s in set(re.findall(r'Sections? (\d(?:\.\d)?)', text)):
    if s not in secs: bad.append('section referenced but missing: ' + s)
n_refs = [int(x) for x in re.findall(r'^(\d+)\. ', refs_txt, re.M)]
cited = set()
for grp in re.findall(r'\[(\d+(?:, ?\d+)*)\]', main + app):
    cited |= {int(x) for x in re.split(r', ?', grp)}
for n in sorted(cited):
    if n not in n_refs: bad.append('citation without reference: [%d]' % n)
for n in n_refs:
    if n not in cited: bad.append('reference never cited: %d' % n)
if n_refs != list(range(1, len(n_refs) + 1)): bad.append('reference numbers not in order')
first = []
for grp in re.findall(r'\[(\d+(?:, ?\d+)*)\]', main + app):
    for x in re.split(r', ?', grp):
        if int(x) not in first: first.append(int(x))
if first != sorted(first): bad.append('citations not numbered by first use: ' + str(first))
left = re.findall(r'\[@[a-z0-9]+', body)
if left: bad.append('unresolved citation keys: ' + str(left))
print('references:', len(n_refs), '| cited:', len(cited))
print('PROBLEMS:', len(bad)); [print('  ', b) for b in bad]
urls = sorted(set(re.findall(r'\((https?://[^)\s]+)\)', body)))
open(sys.argv[2], 'w').write('\n'.join(urls) + '\n')
hosts = sorted({re.match(r'https?://([^/]+)', u).group(1) for u in urls})
print('links:', len(urls), '| hosts:', ' '.join(hosts))
