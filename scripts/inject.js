/* 易班/优课考试页面注入脚本 —— 交给 exam_lib.inject() 执行。
 * 幂等：重复注入不会丢已设置的 answers。
 * 暴露 window.__Y，供 CDP /eval 调用。
 */
(() => {
  const Y = (window.__Y = window.__Y || {});
  Y.answers = Y.answers || {};

  /* ---------- 文本归一化：剥掉选项前缀字母、统一全半角括号、去掉全部标点空白 ---------- */
  Y.norm = function (s) {
    return String(s == null ? '' : s)
      .replace(/^[A-DＡ-Ｄ]\s*[.．、]\s*/, '')
      .replace(/[（(]/g, '(')
      .replace(/[）)]/g, ')')
      .replace(/[\s，,。.；;：:！!？?、·・\-—_—~～"'"'""'']/g, '')
      .trim();
  };

  /* ---------- 选项节点枚举：不依赖 jsx-<hash> 类名 ----------
   * 判据：某个 <ul> 的第一个 <li> 文本以 "A."/"A、" 开头，且所有 <li> 非空。
   * 命中多个时取 li 最多的那个（题目的选项列表通常最长）。
   */
  Y.optNodes = function () {
    const uls = document.querySelectorAll('ul');
    let best = null, bestN = -1;
    for (let i = 0; i < uls.length; i++) {
      const lis = uls[i].querySelectorAll('li');
      if (lis.length < 2) continue;
      if (!/^[AＡ]\s*[.．、]/.test((lis[0].innerText || '').trim())) continue;
      let ok = true;
      for (let j = 0; j < lis.length; j++) {
        if (!(lis[j].innerText || '').trim()) { ok = false; break; }
      }
      if (!ok) continue;
      if (lis.length > bestN) { bestN = lis.length; best = lis; }
    }
    return best ? Array.prototype.slice.call(best) : null;
  };

  /* ---------- 题号 ---------- */
  Y.qnum = function () {
    const h = document.querySelector('main h3') || document.querySelector('h3');
    if (h) {
      const m = (h.innerText || '').match(/^\s*(\d+)\s*[、.．]/);
      if (m) return parseInt(m[1], 10);
    }
    const m2 = document.body.innerText.match(/(\d+)\s*\/\s*(\d+)/);
    return m2 ? parseInt(m2[1], 10) : null;
  };

  Y.qtotal = function () {
    const m = document.body.innerText.match(/(\d+)\s*\/\s*(\d+)/);
    return m ? parseInt(m[2], 10) : null;
  };

  Y.title = function () {
    const h = document.querySelector('main h3') || document.querySelector('h3');
    if (!h) return '';
    return (h.innerText || '')
      .replace(/^\s*\d+\s*[、.．]\s*/, '')
      .replace(/^\s*\[[^\]]*\]\s*/, '')
      .trim();
  };

  /* ---------- 是否已选中 ---------- */
  Y.isSel = function (li) {
    const cn = li.className || '';
    if (/(^|\s)_c(\s|$)/.test(cn)) return true;
    return /_c$/.test(cn.trim());
  };

  /* ---------- 匹配算法（核心，别改成双向 includes！） ----------
   * 1) 归一化后精确相等 → 命中
   * 2) 否则「选项文本包含关键词」→ 命中，但必须唯一
   * 刻意不做「关键词包含选项文本」的反向匹配：
   *   那会让「警告处分」误吃「严重警告处分」、「III级」误吃「II级」。
   */
  Y.pickIndex = function (key, lis) {
    const k = Y.norm(key);
    if (!k) return 'NOANS';
    let c = [];
    for (let i = 0; i < lis.length; i++) {
      if (Y.norm(lis[i].innerText) === k) c.push(i);
    }
    if (c.length === 1) return c[0];
    if (c.length > 1) return 'AMB:' + c.join(',');
    c = [];
    for (let i = 0; i < lis.length; i++) {
      if (Y.norm(lis[i].innerText).indexOf(k) >= 0) c.push(i);
    }
    if (c.length === 1) return c[0];
    if (c.length > 1) return 'AMB:' + c.join(',');
    return 'MISS';
  };

  /* ---------- 读当前页状态 ---------- */
  Y.state = function () {
    const lis = Y.optNodes();
    const opts = [], sel = [];
    if (lis) {
      for (let i = 0; i < lis.length; i++) {
        opts.push((lis[i].innerText || '').trim());
        if (Y.isSel(lis[i])) sel.push(i);
      }
    }
    return { q: Y.qnum(), total: Y.qtotal(), title: Y.title(), opts: opts, sel: sel };
  };

  /* ---------- 一拍：给当前题选答案 ---------- */
  Y.step = function () {
    const lis = Y.optNodes();
    const s = Y.state();
    if (!lis) return { q: s.q, total: s.total, status: 'NOOPT', title: s.title };
    const key = Y.answers[s.q];
    if (!key) return { q: s.q, total: s.total, status: 'NOANS', title: s.title, opts: s.opts };
    const idx = Y.pickIndex(key, lis);
    if (typeof idx !== 'number') {
      return { q: s.q, total: s.total, status: idx, title: s.title, opts: s.opts, key: key };
    }
    if (Y.isSel(lis[idx])) {
      return { q: s.q, total: s.total, status: 'already', idx: idx, title: s.title };
    }
    lis[idx].click();
    return { q: s.q, total: s.total, status: 'clicked', idx: idx, title: s.title };
  };

  /* ---------- 翻页 ---------- */
  Y.nav = function (dir) {
    const want = dir < 0 ? '上一题' : '下一题';
    const bs = document.querySelectorAll('button');
    for (let i = 0; i < bs.length; i++) {
      if ((bs[i].innerText || '').trim() === want) { bs[i].click(); return 'nav'; }
    }
    return 'NONAV';
  };

  /* ---------- 手工干预 ---------- */
  Y.setAnswer = function (q, key) { Y.answers[q] = key; return 'ok'; };
  Y.setAnswers = function (obj) { Object.assign(Y.answers, obj); return Object.keys(obj).length; };
  Y.clickIndex = function (i) {
    const lis = Y.optNodes();
    if (!lis || !lis[i]) return 'NOOPT';
    lis[i].click();
    return 'clicked';
  };

  return JSON.stringify({ injected: true, answers: Object.keys(Y.answers).length });
})()
