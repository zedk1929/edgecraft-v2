(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const money = (value, digits = 0) => new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', maximumFractionDigits: digits, minimumFractionDigits: digits,
  }).format(Number.isFinite(value) ? value : 0);
  const compact = (value) => new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 2,
  }).format(Number.isFinite(value) ? value : 0);
  const percent = (value, digits = 1) => `${value.toFixed(digits)}%`;
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  const valuationDefaults = { price: 42, revenue: 1200, growth: 18, margin: 22, multiple: 24, discount: 10, shares: 120 };
  const betDefaults = { odds: -110, probability: 57, bankroll: 1000, kellyFraction: 0.25 };

  function valueCompany(overrides = {}) {
    const v = {
      price: +$('price').value,
      revenue: +$('revenue').value,
      growth: +$('growth').value,
      margin: +$('margin').value,
      multiple: +$('multiple').value,
      discount: +$('discount').value,
      shares: +$('shares').value,
      ...overrides,
    };

    const years = [v.revenue];
    for (let i = 1; i <= 5; i += 1) years.push(years[i - 1] * (1 + v.growth / 100));
    const cashFlows = years.map((revenue) => revenue * v.margin / 100);
    const terminalValue = cashFlows[5] * v.multiple;
    const presentValue = terminalValue / ((1 + v.discount / 100) ** 5);
    const fairValue = presentValue / v.shares;
    return { ...v, years, cashFlows, terminalValue, presentValue, fairValue };
  }

  function updateValuation() {
    const v = valueCompany();
    $('priceOut').textContent = money(v.price, 2);
    $('revenueOut').textContent = compact(v.revenue * 1e6);
    $('growthOut').textContent = percent(v.growth, 0);
    $('marginOut').textContent = percent(v.margin, 0);
    $('multipleOut').textContent = `${v.multiple}×`;
    $('discountOut').textContent = percent(v.discount, v.discount % 1 ? 1 : 0);
    $('sharesOut').textContent = `${v.shares}M`;
    $('fairValue').textContent = money(v.fairValue, 2);
    $('marketCap').textContent = compact(v.presentValue * 1e6);
    $('futureRevenue').textContent = compact(v.years[5] * 1e6);
    $('revenueCagr').textContent = `${percent(v.growth, 1)} CAGR`;

    const delta = (v.fairValue / v.price - 1) * 100;
    const deltaEl = $('valueDelta');
    deltaEl.textContent = `${delta >= 0 ? '+' : ''}${percent(delta, 1)} vs. price`;
    deltaEl.className = delta >= 0 ? 'positive' : 'negative';
    $('valuationRead').textContent = delta >= 25
      ? 'Wide upside—stress the assumptions before acting.'
      : delta >= 0
        ? 'Upside under this assumption set.'
        : delta >= -15
          ? 'Near market. The thesis needs a tighter catalyst.'
          : 'The market price exceeds this scenario value.';
    $('valuationDot').style.background = delta >= 0 ? 'var(--accent)' : 'var(--danger)';
    renderValuationChart(v);
    renderHeatmap(v);
  }

  function renderValuationChart(v) {
    const max = Math.max(...v.years, 1);
    $('valuationChart').innerHTML = v.years.map((revenue, i) => {
      const fcf = v.cashFlows[i];
      const revenueHeight = Math.max(2, revenue / max * 100);
      const fcfHeight = Math.max(2, fcf / max * 100);
      return `<div class="bar-group">
        <div class="bar" style="height:${revenueHeight}%"></div>
        <div class="bar fcf" style="height:${fcfHeight}%"></div>
        <span class="bar-value">${compact(revenue * 1e6)} / ${compact(fcf * 1e6)}</span>
        <span class="bar-label">${i === 0 ? 'TTM' : `Y${i}`}</span>
      </div>`;
    }).join('');
  }

  function renderHeatmap(v) {
    const growths = [-8, -4, 0, 4, 8].map((n) => clamp(v.growth + n, -10, 60));
    const multiples = [-6, -3, 0, 3, 6].map((n) => clamp(v.multiple + n, 8, 45));
    let html = '<div class="heat-label">GROWTH ↓<br>MULT. →</div>';
    html += multiples.map((m) => `<div class="heat-label">${m}×</div>`).join('');
    growths.forEach((g, row) => {
      html += `<div class="heat-label">${g}%</div>`;
      multiples.forEach((m, col) => {
        const fair = valueCompany({ growth: g, multiple: m }).fairValue;
        const ratio = fair / v.price;
        const hue = clamp(8 + (ratio - 0.65) * 72, 8, 132);
        const light = document.documentElement.dataset.theme === 'light' ? 78 : 25;
        const textLight = document.documentElement.dataset.theme === 'light' ? 17 : 90;
        html += `<div class="heat-cell${row === 2 && col === 2 ? ' current' : ''}" role="gridcell" aria-label="${g}% growth and ${m} times multiple: ${money(fair, 2)}" style="background:hsl(${hue} 56% ${light}%);color:hsl(${hue} 35% ${textLight}%)">${money(fair, 0)}</div>`;
      });
    });
    $('heatmap').innerHTML = html;
  }

  function decimalOdds(american) {
    if (american === 0 || !Number.isFinite(american)) return 1;
    return american > 0 ? 1 + american / 100 : 1 + 100 / Math.abs(american);
  }

  function americanOdds(probability) {
    const p = clamp(probability, 0.001, 0.999);
    const value = p >= 0.5 ? -100 * p / (1 - p) : 100 * (1 - p) / p;
    return `${value > 0 ? '+' : '−'}${Math.round(Math.abs(value))}`;
  }

  function mulberry32(seed) {
    return function random() {
      let t = seed += 0x6D2B79F5;
      t = Math.imul(t ^ t >>> 15, t | 1);
      t ^= t + Math.imul(t ^ t >>> 7, t | 61);
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  function percentile(sorted, p) {
    const index = (sorted.length - 1) * p;
    const low = Math.floor(index);
    const high = Math.ceil(index);
    return sorted[low] + (sorted[high] - sorted[low]) * (index - low);
  }

  function calculateBet() {
    const odds = +$('odds').value;
    const p = +$('probability').value / 100;
    const bankroll = Math.max(0, +$('bankroll').value || 0);
    const fraction = +$('kellyFraction').value;
    const decimal = decimalOdds(odds);
    const b = decimal - 1;
    const marketP = decimal > 1 ? 1 / decimal : 1;
    const edge = p - marketP;
    const ev = p * b - (1 - p);
    const fullKelly = b > 0 ? (b * p - (1 - p)) / b : 0;
    const stakePct = clamp(fullKelly * fraction, 0, 0.25);
    const stake = bankroll * stakePct;
    return { odds, p, bankroll, fraction, decimal, b, marketP, edge, ev, fullKelly, stakePct, stake };
  }

  function updateBet() {
    const bet = calculateBet();
    $('probabilityOut').textContent = percent(bet.p * 100, 0);
    const labels = ['No bet', '¼ Kelly', '½ Kelly', '¾ Kelly', 'Full Kelly'];
    $('kellyFractionOut').textContent = labels[Math.round(bet.fraction * 4)] || `${bet.fraction} Kelly`;
    $('stake').textContent = money(bet.stake, bet.stake < 100 ? 2 : 0);
    $('stakePct').textContent = `${percent(bet.stakePct * 100, 1)} of bankroll`;
    $('expectedValue').textContent = `${bet.ev >= 0 ? '+' : ''}${money(bet.ev * 100, 2)}`;
    $('marketProbability').textContent = percent(bet.marketP * 100, 1);
    $('fairOdds').textContent = `Your fair line: ${americanOdds(bet.p)}`;

    const edge = bet.edge * 100;
    const edgeLabel = $('edgeLabel');
    edgeLabel.textContent = `${edge >= 0 ? '+' : ''}${edge.toFixed(1)} pt edge`;
    edgeLabel.className = edge >= 0 ? 'positive' : 'negative';
    $('expectedValue').style.color = bet.ev >= 0 ? 'var(--accent)' : 'var(--danger)';

    const decision = bet.ev <= 0
      ? 'Negative expected value. Pass at this price.'
      : bet.stakePct === 0
        ? 'Positive edge detected. Sizing is switched off.'
        : bet.stakePct >= 0.15
          ? 'Large theoretical edge. Recheck your probability.'
          : 'Positive edge. Size modestly.';
    $('decisionText').textContent = decision;
    $('decisionStrip').querySelector('.decision-dot').style.background = bet.ev >= 0 ? 'var(--accent)' : 'var(--danger)';
    renderSimulation(bet);
  }

  function renderSimulation(bet) {
    const paths = 400;
    const bets = 100;
    const seed = Math.round((bet.odds + 1000) * 31 + bet.p * 10000 + bet.stakePct * 100000);
    const random = mulberry32(seed);
    const series = [];
    let profitable = 0;
    let deepDrawdown = 0;

    for (let path = 0; path < paths; path += 1) {
      let bank = bet.bankroll;
      let peak = bank;
      let hitDrawdown = false;
      const values = [bank];
      for (let i = 0; i < bets; i += 1) {
        const stake = bank * bet.stakePct;
        bank += random() < bet.p ? stake * bet.b : -stake;
        peak = Math.max(peak, bank);
        if (peak > 0 && bank / peak <= 0.5) hitDrawdown = true;
        values.push(bank);
      }
      if (bank > bet.bankroll) profitable += 1;
      if (hitDrawdown) deepDrawdown += 1;
      series.push(values);
    }

    const q25 = [], median = [], q75 = [];
    for (let i = 0; i <= bets; i += 1) {
      const slice = series.map((path) => path[i]).sort((a, b) => a - b);
      q25.push(percentile(slice, 0.25));
      median.push(percentile(slice, 0.5));
      q75.push(percentile(slice, 0.75));
    }

    const width = 760, height = 220, left = 54, right = 10, top = 14, bottom = 25;
    const maxY = Math.max(...q75, bet.bankroll, 1) * 1.08;
    const minY = Math.min(...q25, bet.bankroll, 0) * 0.92;
    const x = (i) => left + i / bets * (width - left - right);
    const y = (value) => top + (maxY - value) / Math.max(1, maxY - minY) * (height - top - bottom);
    const line = (values) => values.map((value, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(value).toFixed(1)}`).join(' ');
    const band = `${q75.map((value, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(value).toFixed(1)}`).join(' ')} ${q25.slice().reverse().map((value, reverseI) => {
      const i = bets - reverseI;
      return `L${x(i).toFixed(1)},${y(value).toFixed(1)}`;
    }).join(' ')} Z`;
    const gridValues = [minY, (minY + maxY) / 2, maxY];

    $('simulation').innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
      ${gridValues.map((value) => `<line class="grid-line" x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}"></line><text class="axis-text" x="0" y="${y(value) + 3}">${compact(value)}</text>`).join('')}
      <line class="start-line" x1="${left}" x2="${width - right}" y1="${y(bet.bankroll)}" y2="${y(bet.bankroll)}"></line>
      <path class="band" d="${band}"></path>
      <path class="median-line" d="${line(median)}"></path>
      <text class="axis-text" x="${left}" y="${height - 4}">BET 0</text>
      <text class="axis-text" text-anchor="end" x="${width - right}" y="${height - 4}">BET 100</text>
    </svg>`;

    $('medianFinish').textContent = money(median[bets], 0);
    $('profitChance').textContent = percent(profitable / paths * 100, 0);
    $('drawdownRisk').textContent = percent(deepDrawdown / paths * 100, 0);
  }

  function resetInputs(defaults) {
    Object.entries(defaults).forEach(([id, value]) => { $(id).value = value; });
  }

  function copySnapshot() {
    const bet = calculateBet();
    const summary = `Edgecraft bet snapshot\nOdds: ${bet.odds > 0 ? '+' : ''}${bet.odds}\nModel probability: ${percent(bet.p * 100, 1)}\nMarket probability: ${percent(bet.marketP * 100, 1)}\nEV per $100: ${bet.ev >= 0 ? '+' : ''}${money(bet.ev * 100, 2)}\nSuggested stake: ${money(bet.stake, 2)} (${percent(bet.stakePct * 100, 1)} of bankroll)`;
    navigator.clipboard?.writeText(summary).then(() => showToast('Snapshot copied')).catch(() => showToast('Copy unavailable'));
  }

  function copyValuation() {
    const v = valueCompany();
    const delta = (v.fairValue / v.price - 1) * 100;
    const summary = `Edgecraft valuation snapshot\nCurrent price: ${money(v.price, 2)}\nTTM revenue: ${compact(v.revenue * 1e6)}\nGrowth / FCF margin: ${percent(v.growth, 1)} / ${percent(v.margin, 1)}\nTerminal multiple / discount rate: ${v.multiple}× / ${percent(v.discount, 1)}\nModeled fair value: ${money(v.fairValue, 2)} (${delta >= 0 ? '+' : ''}${percent(delta, 1)} vs. price)`;
    navigator.clipboard?.writeText(summary).then(() => showToast('Thesis copied')).catch(() => showToast('Copy unavailable'));
  }

  let toastTimer;
  function showToast(message) {
    const toast = $('toast');
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 1800);
  }

  Object.keys(valuationDefaults).forEach((id) => $(id).addEventListener('input', updateValuation));
  ['odds', 'probability', 'bankroll', 'kellyFraction'].forEach((id) => $(id).addEventListener('input', updateBet));
  $('resetValuation').addEventListener('click', () => { resetInputs(valuationDefaults); updateValuation(); });
  $('resetBet').addEventListener('click', () => { resetInputs(betDefaults); updateBet(); });
  $('copySnapshot').addEventListener('click', copySnapshot);
  $('copyValuation').addEventListener('click', copyValuation);

  document.querySelectorAll('[data-val-preset]').forEach((button) => button.addEventListener('click', () => {
    const presets = {
      bear: { ...valuationDefaults, growth: 8, margin: 14, multiple: 16, discount: 12 },
      base: valuationDefaults,
      bull: { ...valuationDefaults, growth: 28, margin: 30, multiple: 32, discount: 8.5 },
    };
    resetInputs(presets[button.dataset.valPreset]);
    updateValuation();
  }));

  document.querySelectorAll('[data-preset]').forEach((button) => button.addEventListener('click', () => {
    const presets = {
      coin: { odds: -110, probability: 50, bankroll: 1000, kellyFraction: 0.25 },
      dog: { odds: 180, probability: 40, bankroll: 1000, kellyFraction: 0.25 },
      favorite: { odds: -240, probability: 73, bankroll: 1000, kellyFraction: 0.25 },
    };
    resetInputs(presets[button.dataset.preset]);
    updateBet();
  }));

  $('themeToggle').addEventListener('click', () => {
    const light = document.documentElement.dataset.theme !== 'light';
    document.documentElement.dataset.theme = light ? 'light' : 'dark';
    $('themeIcon').textContent = light ? '☾' : '☼';
    localStorage.setItem('edgecraft-theme', light ? 'light' : 'dark');
    updateValuation();
  });

  const savedTheme = localStorage.getItem('edgecraft-theme');
  if (savedTheme === 'light') {
    document.documentElement.dataset.theme = 'light';
    $('themeIcon').textContent = '☾';
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => { if (entry.isIntersecting) entry.target.classList.add('visible'); });
  }, { threshold: 0.08 });
  document.querySelectorAll('.reveal').forEach((element) => observer.observe(element));

  updateValuation();
  updateBet();
})();
