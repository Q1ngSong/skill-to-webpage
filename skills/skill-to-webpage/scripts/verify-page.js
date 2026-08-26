#!/usr/bin/env node
/* skill-to-webpage 页面自动验证(Playwright)
   用法: node scripts/verify-page.js <生成的 workflow.html 路径>
   单页(base.html):占位符残留 / 节点切换 / 子流程图绘制 / 卫星栏 / 步骤展开 /
        主题切换 / 出处开关 / 追问弹窗 / 子流程边选中 / 移动端不溢出(13 项)
   组合总览页(bundle.html,body[data-page="bundle"]):两张图与 skill 数 / 图 1 弧数 /
        图 2 连线数 / 全部展开 / 图 2 连线起点几何 / 成员链接存在(6 项)+ 占位符残留
        (整份扫)、data-source 出处、主题、出处开关、追问弹窗、375px、JS 错误
        7 项共用(13 项) */

var path = require("path");
var fs = require("fs");

var file = process.argv[2];
if (!file) {
  console.error("用法: node scripts/verify-page.js <workflow.html 路径>");
  process.exit(2);
}
file = path.resolve(file);
if (!fs.existsSync(file)) {
  console.error("文件不存在: " + file);
  process.exit(2);
}

var chromium;
try {
  chromium = require("playwright").chromium;
} catch (e) {
  console.error("未安装 playwright。安装: npm i -D playwright && npx playwright install chromium");
  process.exit(2);
}

var results = [];
function check(name, ok, detail) {
  results.push({ name: name, ok: ok, detail: detail || "" });
  console.log((ok ? "  ✓ " : "  ✗ ") + name + (detail ? "  — " + detail : ""));
}

(async function main() {
  /* 静态检查:占位符残留(排除正文里作为示例展示的 {{...}} 代码片段:
     只要 <title>/<body data-theme>/JS 数据槽位没有残留即可) */
  var html = fs.readFileSync(file, "utf8");
  var bundleSlots = ["{{lang}}", "{{title}}", "{{default_theme}}", "{{theme_styles}}", "{{group}}",
    "{{eyebrow}}", "{{hero_html}}", "{{fig1_html}}", "{{fig2_html}}", "{{edges_table}}", "{{stats_table}}",
    "{{recon_html}}", "{{layout_json}}", "{{footer_note}}", "{{flow_lib}}", "{{skill_dirs}}"];
  var criticalSlotSites = {
    "{{lang}}": /<html\b[^>]*\blang=["']\{\{lang\}\}["']/i,
    "{{title}}": /<title>\s*\{\{title\}\}\s*<\/title>/i,
    "{{default_theme}}": /<body\b[^>]*\bdata-theme=["']\{\{default_theme\}\}["']/i,
    "{{theme_styles}}": /\/\* —— 主题层[^*]*\*\/\s*\{\{theme_styles\}\}/i,
    "{{panels}}": /<main\b[^>]*\bid=["']panels["'][^>]*>\s*\{\{panels\}\}/i,
    "{{rail_groups}}": /<div\b(?=[^>]*\bclass=["'][^"']*\brail\b[^"']*["'])(?=[^>]*\bid=["']rail["'])[^>]*>\s*\{\{rail_groups\}\}/i,
    "{{toc_items}}": /<nav\b(?=[^>]*\bclass=["'][^"']*\btoc\b[^"']*["'])(?=[^>]*\bid=["']toc["'])[^>]*>\s*\{\{toc_items\}\}/i,
    "{{nodes_json}}": /\bvar\s+NODES\s*=\s*\{\{nodes_json\}\}/,
    "{{skill_dir}}": /\bvar\s+SKILL_DIR\s*=\s*["']\{\{skill_dir\}\}["']/,
    "{{kb_dir}}": /\bvar\s+KB_DIR\s*=\s*["']\{\{kb_dir\}\}["']/,
    "{{subflow_loops_json}}": /\bvar\s+SUBFLOW_LOOPS\s*=\s*\{\{subflow_loops_json\}\}/,
    "{{initial_node_json}}": /\bvar\s+start\s*=\s*\{\{initial_node_json\}\}/
  };
  var criticalSlots = Object.keys(criticalSlotSites);
  function slotLeaksIn(slots, scanAll) {
    var leaks = [], i;
    for (i = 0; i < slots.length; i++) {
      /* 单 skill 页会原样展示被分析 skill 的正文；正文可能恰好讲解
         {{panels}} 一类模板 token。只检查 token 在 base.html 的骨架位置
         是否残留，避免把教学示例误报成渲染失败。 */
      if (!scanAll && criticalSlotSites[slots[i]]) {
        if (criticalSlotSites[slots[i]].test(html)) { leaks.push(slots[i]); }
      } else if (html.indexOf(slots[i]) !== -1) {
        leaks.push(slots[i]);
      }
    }
    /* 总览页整份都是生成物(base.html 正文里才有当示例展示的 {{…}}),所以不靠固定清单整份扫:
       正文里的残留出坏版式,<script> 里的会让整段 JS 解析失败、页面全瘫。 */
    if (scanAll) {
      var m = html.match(/\{\{[a-z_0-9]+\}\}/g) || [];
      for (i = 0; i < m.length; i++) {
        if (leaks.indexOf(m[i]) === -1) { leaks.push(m[i]); }
      }
    }
    return leaks;
  }
  var browser = await chromium.launch();
  var page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  var pageErrors = [];
  page.on("pageerror", function (err) { pageErrors.push(String(err)); });
  await page.goto("file://" + file);
  await page.waitForTimeout(300);

  /* 页面类型:单页(base.html)/ 组合总览页(bundle.html) */
  var isBundle = await page.evaluate(function () { return document.body.getAttribute("data-page") === "bundle"; });

  var slotLeaks = slotLeaksIn(isBundle ? bundleSlots : criticalSlots, isBundle);
  check("无关键槽位残留", slotLeaks.length === 0, slotLeaks.join(", "));

  /* ——— 组合总览页专属:两张图 / 边数 / 展开开关 / 成员链接 ——— */
  if (isBundle) {
    var bs = await page.evaluate(function () {
      var chips = document.querySelectorAll("#c1 .chip").length;
      var clusters = document.querySelectorAll("#c2 .cluster").length;
      var p1 = document.querySelectorAll("#s1 path.fe").length;
      var p2 = document.querySelectorAll("#s2 path.fe").length;
      var want1 = LAYOUT.fig1.edges.length, want2 = LAYOUT.fig2.edges.length;
      var cb = document.getElementById("expandAll");
      cb.checked = true; cb.onchange();
      var allBoxes = document.querySelectorAll("#c2 .nbox").length;
      var visibleAfter = 0, bx = document.querySelectorAll("#c2 .nbox"), i;
      for (i = 0; i < bx.length; i++) { if (bx[i].offsetParent !== null) { visibleAfter++; } }
      var p2b = document.querySelectorAll("#s2 path.fe").length;
      cb.checked = false; cb.onchange();
      /* 几何自检:每条图 2 连线的起点必须落在**来源节点盒子**上(只算到框内坐标时会全挤在原点;
         只落到分组框边上则说明线连的是 skill 而不是节点) */
      var geomBad = [], ed = LAYOUT.fig2.edges, ps = document.querySelectorAll("#s2 path.fe");
      function c2Rect(el) {
        var l = 0, t = 0, n2 = el, root = document.getElementById("c2");
        while (n2 && n2 !== root) { l += n2.offsetLeft; t += n2.offsetTop; n2 = n2.offsetParent; }
        return { l: l, t: t, r: l + el.offsetWidth, b: t + el.offsetHeight };
      }
      for (i = 0; i < ps.length; i++) {
        /* 端点框不可见的边会被跳过,位置对不上 —— 用 path 自带的 data-i 回指 LAYOUT 里那条边 */
        var ei = parseInt(ps[i].getAttribute("data-i"), 10);
        if (isNaN(ei) || !ed[ei]) { geomBad.push("path[" + i + "] 没有 data-i"); continue; }
        var d = ps[i].getAttribute("d") || "", mm = d.match(/^M\s+(-?[\d.]+)\s+(-?[\d.]+)/);
        var nb = document.querySelector('#c2 .nbox[data-key="' + ed[ei].from + '"]');
        if (!mm || !nb) { geomBad.push(ed[ei].from + " 无起点/无来源节点"); continue; }
        var y = parseFloat(mm[2]), x = parseFloat(mm[1]), bx = c2Rect(nb);
        if (y < bx.t - 2 || y > bx.b + 2 || x < bx.l - 2 || x > bx.r + 2) {
          geomBad.push(ed[ei].from + " 起点 (" + Math.round(x) + "," + Math.round(y) + ") 不在该节点盒子上");
        }
      }
      var hrefs = [], a = document.querySelectorAll("#c1 .chip");
      for (i = 0; i < a.length; i++) { hrefs.push(a[i].getAttribute("href")); }
      return { chips: chips, clusters: clusters, p1: p1, want1: want1, p2: p2, want2: want2,
        allBoxes: allBoxes, visibleAfter: visibleAfter, p2b: p2b, hrefs: hrefs, geomBad: geomBad };
    });
    check("图 1 / 图 2 存在且 skill 数一致", bs.chips > 0 && bs.chips === bs.clusters, bs.chips + " skills / " + bs.clusters + " clusters");
    check("图 1 弧数 = 跨 skill 对数", bs.p1 === bs.want1, bs.p1 + "/" + bs.want1);
    check("图 2 折叠态连线数 = 跨 skill 边数", bs.p2 === bs.want2, bs.p2 + "/" + bs.want2);
    check("全部展开后节点全部可见且连线不变", bs.visibleAfter === bs.allBoxes && bs.p2b === bs.want2,
      bs.visibleAfter + "/" + bs.allBoxes + " 节点 · 线 " + bs.p2b + "/" + bs.want2);
    check("图 2 连线起点落在来源节点上", bs.geomBad.length === 0, bs.geomBad.slice(0, 3).join(" · "));
    var missing = bs.hrefs.filter(function (h) { return !h || !fs.existsSync(path.join(path.dirname(file), h.split("#")[0])); });
    check("skill 卡片链接的成员页面存在", missing.length === 0, missing.join(","));
  }

  /* 节点切换:遍历每个流程带芯片 */
  if (!isBundle) {
    var chips = await page.$$(".node-chip");
    check("节点总览存在节点", chips.length > 0, chips.length + " 个");
    var switchOk = true;
    for (var c = 0; c < chips.length; c++) {
      await chips[c].click();
      var nodeId = await chips[c].getAttribute("data-node");
      var visible = await page.$eval("#p-" + nodeId, function (el) { return el.classList.contains("active"); }).catch(function () { return false; });
      if (!visible) { switchOk = false; }
    }
    check("点击节点均能切换到对应面板", switchOk);

    /* 子流程图:每个 stepper 的 SVG 有边;有环配置的有环边 */
    var sfStats = await page.evaluate(function () {
      var out = [];
      var steppers = document.querySelectorAll(".stepper");
      for (var i = 0; i < steppers.length; i++) {
        var id = steppers[i].id;
        var chip = document.querySelector('.node-chip[data-node="' + steppers[i].closest(".panel").id.replace("p-", "") + '"]');
        if (chip) { chip.click(); }
        var svg = steppers[i].querySelector(".sf-svg");
        out.push({
          id: id,
          nodes: steppers[i].querySelectorAll(".sf-node").length,
          fwd: svg ? svg.querySelectorAll("line").length : 0,
          loops: svg ? svg.querySelectorAll("path.ed-l").length : 0,
          cfgLoops: (window.SUBFLOW_LOOPS && window.SUBFLOW_LOOPS[id]) ? window.SUBFLOW_LOOPS[id].length : 0
        });
      }
      return out;
    });
    var sfOk = true;
    var sfDetail = [];
    for (var s = 0; s < sfStats.length; s++) {
      var st = sfStats[s];
      var expectFwd = st.nodes > 1 ? st.nodes - 1 : 0;
      var ok = st.fwd === expectFwd && st.loops === st.cfgLoops;
      if (!ok) { sfOk = false; }
      sfDetail.push(st.id + ":步" + st.nodes + " 顺" + st.fwd + "/" + expectFwd + " 环" + st.loops + "/" + st.cfgLoops);
    }
    check("子流程图边数正确(顺序边=步骤数-1,环边=配置数)", sfOk, sfDetail.join("; "));

    /* 卫星栏连线(流程带支撑行 / 子流程外部节点栏):条数 = 配置数,且互不重合(轨道 y 与终点两两不同) */
    var laneStats = await page.evaluate(function () {
      function trackY(d) {
        var m = /Q [-\d.]+ ([-\d.]+) /.exec(d);
        /* 无拐点的直线没有横向轨道:按终点 (x,y) 取键,两条不同 x 的竖线不算同轨 */
        var v = / L ([-\d.]+) ([-\d.]+)$/.exec(d);
        return m ? m[1] : "v" + (v ? v[1] + "," + v[2] : "?");
      }
      function endPt(d) { var m = / L ([-\d.]+) ([-\d.]+)$/.exec(d); return m ? m[1] + "," + m[2] : d; }
      function inspect(paths) {
        var ys = {}, ends = {}, i, dupY = 0, dupEnd = 0;
        for (i = 0; i < paths.length; i++) {
          var d = paths[i].getAttribute("d") || "";
          var y = trackY(d), e = endPt(d);
          if (ys[y]) { dupY++; } ys[y] = 1;
          if (ends[e]) { dupEnd++; } ends[e] = 1;
        }
        return { n: paths.length, dupY: dupY, dupEnd: dupEnd };
      }
      var out = [];
      var railSvg = document.getElementById("railSvg");
      if (railSvg) {
        var r = inspect(railSvg.querySelectorAll("path.rl-d"));
        r.id = "rail"; r.want = (window.RAIL_LINKS || []).length; out.push(r);
      }
      var steppers = document.querySelectorAll(".stepper");
      for (var s = 0; s < steppers.length; s++) {
        var lane = steppers[s].querySelector(".sf-lane");
        if (!lane) { continue; }
        var chip = document.querySelector('.node-chip[data-node="' + steppers[s].closest(".panel").id.replace("p-", "") + '"]');
        if (chip) { chip.click(); }
        var want = 0, exts = lane.querySelectorAll(".sf-ext");
        for (var k = 0; k < exts.length; k++) { want += (exts[k].getAttribute("data-at") || exts[k].getAttribute("data-from") || "").split(",").length; }
        var st = inspect(steppers[s].querySelectorAll(".sf-svg path.ed-d, .sf-svg path.ed-x"));
        st.id = steppers[s].id; st.want = want; out.push(st);
      }
      return out;
    });
    if (laneStats.length > 0) {
      var laneOk = true, laneDetail = [];
      for (var l = 0; l < laneStats.length; l++) {
        var ls = laneStats[l];
        if (ls.n !== ls.want || ls.dupY > 0 || ls.dupEnd > 0) { laneOk = false; }
        laneDetail.push(ls.id + ":" + ls.n + "/" + ls.want + " 线" + (ls.dupY ? " 同轨" + ls.dupY : "") + (ls.dupEnd ? " 同终点" + ls.dupEnd : ""));
      }
      check("支撑行与外部节点连线数=配置数且互不重合", laneOk, laneDetail.join("; "));
    }

    /* 子步骤点击展开 explain-card */
    var stepOk = await page.evaluate(function () {
      var stepper = document.querySelector(".stepper");
      if (!stepper) { return true; }
      var btns = stepper.querySelectorAll(".sf-node");
      if (btns.length < 2) { return true; }
      btns[1].click();
      var target = btns[1].getAttribute("data-x");
      var card = document.getElementById(target);
      return card && card.classList.contains("active");
    });
    check("点击子步骤可展开对应说明卡", stepOk);
  } /* end 单页专属 */

  /* 主题切换:4 套逐一设置并确认 body 属性 */
  var themes = ["docs", "blueprint", "ide", "whiteboard"];
  var themeOk = true;
  for (var t = 0; t < themes.length; t++) {
    await page.selectOption("#themePicker", themes[t]).catch(function () { themeOk = false; });
    var cur = await page.evaluate(function () { return document.body.getAttribute("data-theme"); });
    if (cur !== themes[t]) { themeOk = false; }
  }
  check("4 套主题均可切换", themeOk);

  /* 出处:data-source 覆盖 + 开关 */
  var srcCount = await page.$$eval("[data-source]", function (els) { return els.length; });
  check("存在 data-source 出处标注", srcCount > 0, srcCount + " 处");
  await page.click("#srcToggle");
  var srcOn = await page.evaluate(function () { return document.body.classList.contains("show-sources"); });
  check("出处开关可切换", srcOn);

  /* 追问弹窗:单页直接调 openDeepDive;总览页点边清单里的追问按钮(走委托处理器,是真实用户路径) */
  var ddOk = await page.evaluate(function () {
    if (typeof window.openDeepDive !== "function") { return false; }
    if (document.body.getAttribute("data-page") === "bundle") {
      var btn = document.querySelector(".tbl .deep-dive-btn");
      if (!btn) { return false; }
      btn.click();
    } else {
      window.openDeepDive("验证概念", "SKILL.md:1-5");
    }
    var overlay = document.getElementById("ddOverlay");
    var open = overlay && overlay.classList.contains("active");
    var cancel = document.getElementById("ddCancel");
    if (cancel && cancel.onclick) { cancel.onclick(); }
    return open;
  });
  check("追问弹窗可打开", ddOk);

  /* 子流程边可点选:点第一条线 → 该线 .focus,两端盒子 .focus,同图其余淡出;Esc 清空 */
  if (!isBundle) {
    var sfFocus = await page.evaluate(function () {
      var st = null, sts = document.querySelectorAll(".stepper"), i;
      for (i = 0; i < sts.length; i++) {
        var chip = document.querySelector('.node-chip[data-node="' + sts[i].closest(".panel").id.replace("p-", "") + '"]');
        if (chip) { chip.click(); }
        if (sts[i].querySelectorAll(".sfe").length > 0) { st = sts[i]; break; }
      }
      if (!st) { return { skip: true }; }
      st.querySelector(".sfe").dispatchEvent(new MouseEvent("click", { bubbles: true }));
      var r = { focusE: st.querySelectorAll(".sfe.focus").length,
                focusB: st.querySelectorAll(".sf-node.focus, .sf-ext.focus, .sf-end.focus").length,
                dimAny: st.querySelectorAll(".sfe.dim, .sf-node.dim, .sf-ext.dim, .sf-end.dim").length };
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      r.afterEsc = st.querySelectorAll(".focus, .dim").length;
      return r;
    });
    check("子流程边可点选并高亮两端", sfFocus.skip === true
      || (sfFocus.focusE === 1 && sfFocus.focusB >= 1 && sfFocus.dimAny >= 1 && sfFocus.afterEsc === 0),
      sfFocus.skip ? "该页无子流程边" : ("选中线 " + sfFocus.focusE + " · 高亮端点 " + sfFocus.focusB
        + " · 淡出 " + sfFocus.dimAny + " · Esc 后残留 " + sfFocus.afterEsc));
  }

  /* 移动端不溢出 */
  await page.setViewportSize({ width: 375, height: 812 });
  await page.waitForTimeout(250);
  var overflow = await page.evaluate(function () {
    return document.documentElement.scrollWidth - document.documentElement.clientWidth;
  });
  check("375px 视口无横向溢出", overflow <= 1, "溢出 " + overflow + "px");

  check("页面无 JS 运行错误", pageErrors.length === 0, pageErrors.slice(0, 2).join(" | "));

  await browser.close();

  var fails = results.filter(function (r) { return !r.ok; });
  console.log("");
  console.log(fails.length === 0
    ? "PASS — " + results.length + " 项全部通过"
    : "FAIL — " + fails.length + "/" + results.length + " 项未过");
  process.exit(fails.length === 0 ? 0 : 1);
})().catch(function (err) {
  console.error("验证脚本异常: " + err);
  process.exit(2);
});
