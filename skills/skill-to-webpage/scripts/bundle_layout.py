"""组合总览页布局:纯函数,仅标准库。输入 skill 名列表与有向边 (from, to),输出层、顺序与坐标。"""


def break_cycles(names, edges):
    """DFS 找回边。返回 (forward_edges, back_edges)。

    互调对 (a,b),(b,a):先被 DFS 走到的方向留在 forward,反向记为回边。
    遍历按名字排序进行,结果只取决于边集合,与 names / edges 的给出顺序无关。"""
    es = []
    for a, b in edges:
        if a != b and (a, b) not in es:
            es.append((a, b))
    adj = {n: [] for n in names}
    for a, b in sorted(es):
        adj.setdefault(a, []).append(b)
    color = {n: 0 for n in names}
    rm = set()

    def dfs(u):
        color[u] = 1
        for v in adj.get(u, []):
            if color.get(v, 0) == 1:
                rm.add((u, v))
            elif color.get(v, 0) == 0:
                dfs(v)
        color[u] = 2

    for n in sorted(names):
        if color.get(n, 0) == 0:
            dfs(n)
    fwd = [e for e in es if e not in rm]
    back = [e for e in es if e in rm]
    return fwd, back


def mutual_pairs(edges):
    """互调对:两个方向都存在的边(自环除外)。返回有向边集合。"""
    es = {(a, b) for a, b in edges if a != b}
    return {(a, b) for a, b in es if (b, a) in es}


def layer_skills(names, edges):
    """最长路径分层(入口 = 无前向入边)。返回 (layers: [[name…]…], isolated: [name…])。

    互调边(两个方向都存在)不参与分层:二者各按其余入边定层,分完再拉到较深的一层,
    保证互调对**总在同一层**(规范 §5.2);同层内相邻由 order_layers 保证。
    层内与孤立列按名字排序,结果只取决于图本身,与 names 的给出顺序无关。"""
    fwd, _back = break_cycles(names, edges)
    touched = {a for a, b in edges if a != b} | {b for a, b in edges if a != b}
    isolated = sorted(n for n in names if n not in touched)
    active = sorted(n for n in names if n in touched)
    mutual = mutual_pairs(edges)
    preds = {n: [a for a, b in fwd if b == n and (a, b) not in mutual] for n in active}
    depth = {}

    def d(n, seen=()):
        if n in depth:
            return depth[n]
        if n in seen:
            return 0
        ps = [p for p in preds.get(n, []) if p in preds]
        depth[n] = 1 + max(d(p, seen + (n,)) for p in ps) if ps else 0
        return depth[n]

    for n in active:
        d(n)
    pairs = sorted((a, b) for a, b in mutual if a < b)
    for _ in range(len(active) + 1):   # 互调对可能串成链,拉平到不动点
        moved = False
        for a, b in pairs:
            if depth[a] != depth[b]:
                depth[a] = depth[b] = max(depth[a], depth[b])
                moved = True
        if not moved:
            break
    layers = []
    for n in active:
        while len(layers) <= depth[n]:
            layers.append([])
        layers[depth[n]].append(n)
    return [sorted(l) for l in layers if l], isolated


def order_layers(layers, edges, passes=4):
    """重心排序减少交叉:自上而下用上层邻居平均位置排序,再自下而上一遍;互调对保持相邻。"""
    pos = {}
    out = [list(l) for l in layers]
    for i, l in enumerate(out):
        for j, n in enumerate(l):
            pos[n] = (i, j)
    nbrs = {}
    for a, b in edges:
        nbrs.setdefault(a, []).append(b)
        nbrs.setdefault(b, []).append(a)
    for _ in range(passes):
        for i in list(range(1, len(out))) + list(range(len(out) - 2, -1, -1)):
            ref_layer = i - 1 if i > 0 else i + 1

            def bary(n, ref=ref_layer):
                xs = [pos[m][1] for m in nbrs.get(n, []) if pos.get(m, (None,))[0] == ref]
                return sum(xs) / len(xs) if xs else pos[n][1]
            out[i].sort(key=bary)
            for j, n in enumerate(out[i]):
                pos[n] = (i, j)
    for a, b in sorted(mutual_pairs(edges)):
        if a not in pos or b not in pos:
            continue
        if pos[a][0] == pos[b][0] and abs(pos[a][1] - pos[b][1]) > 1:
            l = out[pos[a][0]]
            l.remove(b)
            l.insert(l.index(a) + 1, b)
            for j, n in enumerate(l):
                pos[n] = (pos[n][0], j)
    return out


def place_chips(layers, chip_w=150, gap_x=24, row_h=80, min_w=600):
    """每层水平居中(等宽芯片,图 1)。返回 {name: {x,y,w,layer,index}},总宽由调用方取 max(x+w)。
    图 2 的分组框宽高随节点数变化、行高逐层不同,由 render_bundle.node_graph 自己摆。"""
    pos = {}
    total_w = min_w
    for l in layers:
        total_w = max(total_w, chip_w * len(l) + gap_x * (len(l) - 1))
    for i, l in enumerate(layers):
        ws = [chip_w] * len(l)
        row_w = sum(ws) + gap_x * (len(l) - 1)
        x = (total_w - row_w) / 2
        for j, n in enumerate(l):
            pos[n] = {"x": x, "y": i * row_h, "w": ws[j], "layer": i, "index": j}
            x += ws[j] + gap_x
    return pos
