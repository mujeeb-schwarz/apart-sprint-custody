"""Build the reference click-through page from the built report: each sentence of the
main text that cites a source, followed by each source with its link."""
import re, sys
src = open(sys.argv[1], encoding='utf-8').read()
stamp = sys.argv[3]
body = re.sub(r'^---\n.*?\n---\n', '', src, flags=re.S)
main, rest = body.split('\n## References\n', 1)
refs_txt, app = rest.split('\n## Appendix A', 1)
app = '## Appendix A' + app
refs = {int(m.group(1)): m.group(2).strip() for m in re.finditer(r'^(\d+)\. (.+)$', refs_txt, re.M)}
CITE = re.compile(r'\[(\d+(?:, ?\d+)*)\]')
def nums(s):
    out = []
    for g in CITE.findall(s):
        for x in re.split(r', ?', g):
            if int(x) not in out: out.append(int(x))
    return out
def sentences(t):
    parts = re.split(r'(?<=[.?!])\s+(?=[A-Z“"(*])', t)
    out = []
    for p in parts:
        if out and (out[-1].count('**') % 2 == 1 or out[-1].count('(') > out[-1].count(')')):
            out[-1] += ' ' + p       # do not split inside bold text or brackets
        else:
            out.append(p)
    return out
out = ['# Reference check: every citation in the final report with its source', '',
       f'Made on {stamp} Pacific from the built report (`report_work/draft/REPORT.md`) by `report_work/build/make_reference_check.py`, so the numbers match the final PDF. '
       'Each block gives a sentence of the main text that cites a source, then each source with its link. Click a link and compare it with the sentence. '
       'The appendices cite further sources, listed at the end. Two links (hhs.gov and iso.org) refuse automated requests and open normally in a browser.', '']
k = 0; section = None; shown = set()
for line in main.split('\n'):
    s = line.strip()
    if not s or s.startswith('<!--') or s.startswith('|---'): continue
    h = re.match(r'^##+ (.*)$', s)
    if h: section = h.group(1); continue
    if s.startswith('!['): s = re.sub(r'^!\[(.*)\]\([^)]*\)$', r'\1', s)
    units = [s] if s.startswith('|') else sentences(re.sub(r'^(?:[-*]|\d+\.)\s+', '', s))
    for u in units:
        ns = nums(u)
        if not ns: continue
        k += 1
        label = f'*{section}.* ' if section and section not in shown else ''
        shown.add(section)
        out += [f'**{k}.** {label}{u}', ''] + [f'- [{n}] {refs[n]}' for n in ns] + ['']
main_cited = set(nums(main))
only = [n for n in sorted(refs) if n not in main_cited]
if only:
    out += ['## Sources cited only in the appendices', '']
    for n in only:
        where = sorted({m.group(1) for m in re.finditer(r'^## Appendix ([A-Z])\.', app, re.M)
                        if n in nums(app[m.start():app.find('\n## Appendix', m.end()) if app.find('\n## Appendix', m.end()) > 0 else len(app)])})
        out += [f'- [{n}] {refs[n]} (cited in Appendix {", ".join(where)})']
    out += ['']
open(sys.argv[2], 'w', encoding='utf-8').write('\n'.join(out))
print('sentences with citations:', k, '| references:', len(refs), '| cited in the main text:', len(main_cited), '| appendix only:', only)
