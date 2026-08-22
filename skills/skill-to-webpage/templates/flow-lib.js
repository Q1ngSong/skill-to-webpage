/* 一维放置:每个盒子想居中于其关联盒子正下方;与邻居重叠则并成一簇共同居中;簇不越过左界 minLeft */
function semPlace1D(items, minLeft, gap) {
  items.sort(function (p, q) { return p.want - q.want; });
  var clusters = [];
  var i, k;
  for (i = 0; i < items.length; i++) {
    items[i].off = 0;
    var c = { items: [items[i]], w: items[i].w, sum: items[i].want, left: Math.max(minLeft, items[i].want) };
    while (clusters.length > 0 && clusters[clusters.length - 1].left + clusters[clusters.length - 1].w + gap > c.left) {
      var p = clusters.pop();
      for (k = 0; k < c.items.length; k++) { c.items[k].off += p.w + gap; p.items.push(c.items[k]); }
      p.sum += c.sum - c.items.length * (p.w + gap);
      p.w += gap + c.w;
      p.left = Math.max(minLeft, p.sum / p.items.length);
      c = p;
    }
    clusters.push(c);
  }
  for (i = 0; i < clusters.length; i++) {
    for (k = 0; k < clusters[i].items.length; k++) { clusters[i].items[k].left = clusters[i].left + clusters[i].items[k].off; }
  }
}

/* 正交折线:(x0,y0) 先竖直到轨道 yt,再水平,再竖直到 (x1,y1);拐角圆弧半径 r */
function orthoPath(x0, y0, x1, y1, yt, r) {
  function f(v) { return Math.round(v * 10) / 10; }
  var dx = x1 - x0;
  if (Math.abs(dx) < 2) { return "M " + f(x0) + " " + f(y0) + " L " + f(x1) + " " + f(y1); }
  var sx = dx > 0 ? 1 : -1;
  var s0 = yt > y0 ? 1 : -1;
  var s1 = y1 > yt ? 1 : -1;
  var rr = Math.min(r, Math.abs(dx) / 2, Math.abs(yt - y0), Math.abs(y1 - yt));
  return "M " + f(x0) + " " + f(y0) + " L " + f(x0) + " " + f(yt - s0 * rr) + " Q " + f(x0) + " " + f(yt) + " " + f(x0 + sx * rr) + " " + f(yt) +
    " L " + f(x1 - sx * rr) + " " + f(yt) + " Q " + f(x1) + " " + f(yt) + " " + f(x1) + " " + f(yt + s1 * rr) + " L " + f(x1) + " " + f(y1);
}

/* 卫星栏布线:主行在上、卫星栏在下,轨道夹在两者之间(yTop..yBot)。
   links = [{rowBox, satBox, rowKey, satKey, dir:"up"|"down"}]:up = 箭头汇入主行盒子(依赖来源),down = 箭头汇入卫星盒子(兜底去向)。
   端口沿盒边按对侧盒子的横向位置排序分散;每条线独占一条水平轨道;轨道次序取交叉最少者(≤8 条穷举,更多用邻换贪心)。 */
function semRouteLane(links, yTop, yBot) {
  var i, j, g, cc;
  function spread(keyName, boxName, otherName, portName) {
    var groups = {};
    for (i = 0; i < links.length; i++) {
      if (!groups[links[i][keyName]]) { groups[links[i][keyName]] = []; }
      groups[links[i][keyName]].push(links[i]);
    }
    for (g in groups) {
      if (!groups.hasOwnProperty(g)) { continue; }
      var arr = groups[g];
      arr.sort(function (p, q) { return (p[otherName].l + p[otherName].w / 2) - (q[otherName].l + q[otherName].w / 2); });
      for (j = 0; j < arr.length; j++) { arr[j][portName] = arr[j][boxName].l + arr[j][boxName].w * (j + 1) / (arr.length + 1); }
    }
  }
  spread("rowKey", "rowBox", "satBox", "xs");
  spread("satKey", "satBox", "rowBox", "xe");
  for (i = 0; i < links.length; i++) {
    links[i].lo = Math.min(links[i].xs, links[i].xe);
    links[i].hi = Math.max(links[i].xs, links[i].xe);
    links[i].span = links[i].hi - links[i].lo;
  }
  /* up 在上轨、dn 在下轨时的交叉数:dn 的上竖段穿过 up 的横段 / up 的下竖段穿过 dn 的横段 */
  function pairCross(up, dn) {
    var c = 0;
    if (dn.xs > up.lo + 0.5 && dn.xs < up.hi - 0.5) { c++; }
    if (up.xe > dn.lo + 0.5 && up.xe < dn.hi - 0.5) { c++; }
    return c;
  }
  function cost(order) {
    var c = 0, a, b;
    for (a = 0; a < order.length; a++) { for (b = a + 1; b < order.length; b++) { c += pairCross(order[a], order[b]); } }
    return c;
  }
  function drift(order) { var s = 0, a; for (a = 0; a < order.length; a++) { s += a * order[a].span; } return s; }
  var best = links.slice().sort(function (p, q) { return q.span - p.span; });
  var bestC = cost(best), bestD = drift(best);
  var n = best.length;
  if (n > 1 && n <= 8) {
    var arr2 = best.slice(), cnt = [], k = 0, tmp, sw;
    for (i = 0; i < n; i++) { cnt[i] = 0; }
    while (k < n) {
      if (cnt[k] < k) {
        sw = (k % 2 === 0) ? 0 : cnt[k];
        tmp = arr2[sw]; arr2[sw] = arr2[k]; arr2[k] = tmp;
        cc = cost(arr2);
        if (cc < bestC || (cc === bestC && drift(arr2) < bestD)) { best = arr2.slice(); bestC = cc; bestD = drift(arr2); }
        cnt[k] += 1; k = 0;
      } else { cnt[k] = 0; k += 1; }
    }
  } else if (n > 8) {
    var pass, improved = true;
    for (pass = 0; pass < 30 && improved; pass++) {
      improved = false;
      for (i = 0; i + 1 < n; i++) {
        var t1 = best[i]; best[i] = best[i + 1]; best[i + 1] = t1;
        cc = cost(best);
        if (cc < bestC) { bestC = cc; improved = true; } else { best[i + 1] = best[i]; best[i] = t1; }
      }
    }
  }
  for (i = 0; i < n; i++) {
    var lk = best[i];
    var yt = yTop + (yBot - yTop) * (i + 1) / (n + 1);
    if (lk.dir === "down") {
      lk.d = orthoPath(lk.xs, lk.rowBox.t + lk.rowBox.h + 1, lk.xe, lk.satBox.t - 2, yt, 8);
    } else {
      lk.d = orthoPath(lk.xe, lk.satBox.t - 1, lk.xs, lk.rowBox.t + lk.rowBox.h + 3, yt, 8);
    }
  }
  return best;
}
