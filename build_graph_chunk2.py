import re, os, json, ast
from collections import defaultdict

project_root = '/home/victordcss/Documentos/Huawei-Manager'

# Map coverage filename stems to actual source file paths
chunk2_paths = {
    'src/huawei_manager/__init__': 'src/huawei_manager/handlers/__init__.py',
    'src/huawei_manager/_app': 'src/huawei_manager/_app.py',
    'src/huawei_manager/_protocols': 'src/huawei_manager/_protocols.py',
    'src/huawei_manager/app': 'src/huawei_manager/app.py',
    'src/huawei_manager/app_threading': 'src/huawei_manager/app_threading.py',
    'src/huawei_manager/audit_log': 'src/huawei_manager/audit_log.py',
    'src/huawei_manager/constants': 'src/huawei_manager/constants.py',
    'src/huawei_manager/services_data': 'src/huawei_manager/services_data.py',
    'src/huawei_manager/session': 'src/huawei_manager/session.py',
    'src/huawei_manager/topology': 'src/huawei_manager/topology.py',
    'src/huawei_manager/vault': 'src/huawei_manager/vault.py',
    'src/huawei_manager/vnf_crypto': 'src/huawei_manager/vnf_crypto.py',
    'src/huawei_manager/vnf_probe': 'src/huawei_manager/vnf_probe.py',
    # handlers (from hash c7f9a56d)
    'src/huawei_manager/auth': 'src/huawei_manager/handlers/auth.py',
    'src/huawei_manager/commands': 'src/huawei_manager/handlers/commands.py',
    'src/huawei_manager/dashboard': 'src/huawei_manager/handlers/dashboard.py',
    'src/huawei_manager/fetch': 'src/huawei_manager/handlers/fetch.py',
    'src/huawei_manager/services': 'src/huawei_manager/handlers/services.py',
    'src/huawei_manager/ssh': 'src/huawei_manager/handlers/ssh.py',
    'src/huawei_manager/vnfs': 'src/huawei_manager/handlers/vnfs.py',
    # agents/scans (from hash e101ffa8)
    'tools/cross_ref': 'src/huawei_manager/agents/scans/cross_ref.py',
    'tools/dead_code': 'src/huawei_manager/agents/scans/dead_code.py',
    'tools/deps': 'src/huawei_manager/agents/scans/deps.py',
    'tools/security': 'src/huawei_manager/agents/scans/security.py',
    'tools/structure': 'src/huawei_manager/agents/scans/structure.py',
}

all_sources = {}
for label, path in sorted(chunk2_paths.items()):
    fpath = os.path.join(project_root, path)
    if os.path.exists(fpath):
        with open(fpath) as f:
            src = f.read()
        all_sources[label] = src
        print(f"  OK {label} ({len(src)} chars)")
    else:
        print(f"  MISS {path}")

print(f"\nTotal modules: {len(all_sources)}")

nodes = []
edges = []
hyperedges = []
nid = [0]
def new_id(): nid[0] += 1; return f"n{nid[0]:03d}"

known_labels = {}
parsed = {}  # label -> (tree, node_id)

# Module nodes
for mod_name, src in sorted(all_sources.items()):
    try:
        tree = ast.parse(src)
        doc = ast.get_docstring(tree) or ''
        mod_id = new_id()
        file_path = chunk2_paths[mod_name]
        nodes.append({'id': mod_id, 'kind': 'module', 'label': mod_name, 'file': file_path, 'line': 1, 'doc': doc[:200]})
        known_labels[mod_name] = mod_id
        short = mod_name.split('/')[-1]
        known_labels[short] = mod_id
        parsed[mod_name] = (tree, mod_id)
    except SyntaxError as e:
        print(f"  SYNTAX ERROR {mod_name}: {e.msg}")

for mod_name, (tree, mod_id) in sorted(parsed.items(), key=lambda x: x[0]):
    for n in ast.iter_child_nodes(tree):
        if isinstance(n, ast.Import):
            for alias in n.names:
                lbl = alias.asname or alias.name
                if lbl not in known_labels:
                    imp_id = new_id()
                    nodes.append({'id': imp_id, 'kind': 'module', 'label': lbl, 'file': alias.name, 'line': n.lineno})
                    known_labels[lbl] = imp_id
                edges.append({'source': mod_id, 'target': known_labels[lbl], 'kind': 'imports', 'weight': 1})
        elif isinstance(n, ast.ImportFrom):
            for alias in n.names:
                lbl = alias.asname or alias.name
                full = f"{n.module}.{alias.name}" if n.module else alias.name
                if lbl not in known_labels:
                    imp_id = new_id()
                    nodes.append({'id': imp_id, 'kind': 'module', 'label': lbl, 'file': full, 'line': n.lineno})
                    known_labels[lbl] = imp_id
                edges.append({'source': mod_id, 'target': known_labels[lbl], 'kind': 'imports', 'weight': 1})

    for n in ast.iter_child_nodes(tree):
        if isinstance(n, ast.ClassDef):
            cdoc = ast.get_docstring(n) or ''
            cls_id = new_id()
            file_path = chunk2_paths[mod_name]
            nodes.append({'id': cls_id, 'kind': 'class', 'label': n.name, 'file': file_path, 'line': n.lineno, 'doc': cdoc[:200]})
            edges.append({'source': mod_id, 'target': cls_id, 'kind': 'defines', 'weight': 1})
            known_labels[n.name] = cls_id
            for base in n.bases:
                if isinstance(base, ast.Name):
                    tgt = known_labels.get(base.id, base.id)
                    edges.append({'source': cls_id, 'target': tgt, 'kind': 'inherits', 'weight': 1})
            for item in n.body:
                if isinstance(item, ast.FunctionDef):
                    mdoc = ast.get_docstring(item) or ''
                    mth_id = new_id()
                    nodes.append({'id': mth_id, 'kind': 'function', 'label': f"{n.name}.{item.name}", 'file': file_path, 'line': item.lineno, 'doc': mdoc[:200]})
                    edges.append({'source': cls_id, 'target': mth_id, 'kind': 'defines', 'weight': 1})
        elif isinstance(n, ast.FunctionDef):
            fdoc = ast.get_docstring(n) or ''
            fn_id = new_id()
            file_path = chunk2_paths[mod_name]
            nodes.append({'id': fn_id, 'kind': 'function', 'label': n.name, 'file': file_path, 'line': n.lineno, 'doc': fdoc[:200]})
            edges.append({'source': mod_id, 'target': fn_id, 'kind': 'defines', 'weight': 1})
            known_labels[f"{mod_name}::{n.name}"] = fn_id
            known_labels[n.name] = fn_id
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    c_id = new_id()
                    file_path = chunk2_paths[mod_name]
                    nodes.append({'id': c_id, 'kind': 'constant', 'label': t.id, 'file': file_path, 'line': n.lineno})
                    edges.append({'source': mod_id, 'target': c_id, 'kind': 'defines', 'weight': 1})
                    known_labels[t.id] = c_id

    class CallCollector(ast.NodeVisitor):
        def __init__(self):
            self.calls = []
        def visit_Call(self, n):
            if isinstance(n.func, ast.Attribute):
                self.calls.append(ast.unparse(n.func))
            elif isinstance(n.func, ast.Name):
                self.calls.append(n.func.id)
            self.generic_visit(n)
    cc = CallCollector()
    cc.visit(tree)
    for c in cc.calls[:100]:
        tgt = known_labels.get(c, c)
        edges.append({'source': mod_id, 'target': tgt, 'kind': 'calls', 'weight': 1})

    class NameCollector(ast.NodeVisitor):
        def __init__(self):
            self.names = set()
        def visit_Name(self, n):
            if isinstance(n.ctx, ast.Load):
                self.names.add(n.id)
            self.generic_visit(n)
    nc = NameCollector()
    nc.visit(tree)
    for other_mod, (_, oid) in parsed.items():
        if other_mod == mod_name:
            continue
        other_nc = NameCollector()
        other_nc.visit(parsed[other_mod][0])
        shared = nc.names & other_nc.names
        if shared and len(shared) >= 2:
            hyperedges.append({
                'nodes': [mod_id, oid],
                'kind': 'shares_data_with',
                'label': f"shared names: {', '.join(sorted(shared)[:5])}"
            })

for e in edges:
    if isinstance(e['target'], str) and e['target'] in known_labels:
        e['target'] = known_labels[e['target']]

graph = {
    "chunk": "02",
    "total_chunks": "03",
    "graph": {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": hyperedges
    }
}

out_dir = '/home/victordcss/Documentos/Huawei-Manager/graphify-out'
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, '.graphify_chunk_02.json')
with open(out_path, 'w') as f:
    json.dump(graph, f, indent=2, ensure_ascii=False)

print(f"\nWritten to {out_path}")
print(f"Generated {len(nodes)} nodes, {len(edges)} edges, {len(hyperedges)} hyperedges")
kinds = defaultdict(int)
for n in nodes: kinds[n['kind']] += 1
for k, v in sorted(kinds.items()): print(f"  {k}: {v}")
ekinds = defaultdict(int)
for e in edges: ekinds[e['kind']] += 1
for k, v in sorted(ekinds.items()): print(f"  {k}: {v}")

class SummaryWalker(ast.NodeVisitor):
    def __init__(self):
        self.classes = []
        self.funcs = []
        self.consts = []
    def visit_ClassDef(self, n):
        methods = [x.name for x in n.body if isinstance(x, ast.FunctionDef)]
        self.classes.append((n.name, n.lineno, methods))
        self.generic_visit(n)
    def visit_FunctionDef(self, n):
        self.funcs.append((n.name, n.lineno))
    def visit_Assign(self, n):
        for t in n.targets:
            if isinstance(t, ast.Name) and t.id.isupper():
                self.consts.append((t.id, n.lineno))

print("\n\n=== Module Summaries ===")
for mod_name, src in sorted(all_sources.items()):
    try:
        tree = ast.parse(src)
        sw = SummaryWalker()
        sw.visit(tree)
        if sw.classes or sw.funcs or sw.consts:
            print(f"\n--- {mod_name} ---")
            if sw.classes:
                for c, ln, methods in sw.classes:
                    print(f"  class {c} (L{ln}): {', '.join(methods[:8])}")
            if sw.funcs:
                for f, ln in sw.funcs[:10]:
                    print(f"  def {f} (L{ln})")
            if sw.consts:
                print(f"  constants: {', '.join(c for c, _ in sw.consts[:15])}")
    except SyntaxError:
        pass
