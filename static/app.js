/**
 * FinFlow NBFC Dashboard — app.js
 * ═══════════════════════════════════════════════════════════════
 * Modules:
 *   ThemeManager      — dark/light toggle with localStorage
 *   Toast             — slide-in notification system
 *   TabManager        — animated tab switching
 *   API               — typed fetch wrapper
 *   LoanCalculator    — real-time EMI with debounce
 *   OTPWorkflow       — send → modal → verify → JWT success
 *   ComplianceWorkflow— KFS generation, delivery tracker, audit trail
 * ═══════════════════════════════════════════════════════════════
 */

'use strict';

/* ─────────────────────────────────── helpers ──────────────────── */

/** Format a number as Indian Rupee string with 2 decimal places. */
function fmtINR(val) {
  const n = parseFloat(val);
  if (isNaN(n)) return '₹0.00';
  return '₹' + n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Return a debounced version of fn that fires after `ms` ms of silence. */
function debounce(fn, ms) {
  let t;
  return function (...args) {
    clearTimeout(t);
    t = setTimeout(() => fn.apply(this, args), ms);
  };
}

/**
 * Estimate effective (reducing-balance) APR from a flat rate using
 * Newton-Raphson root-finding on the annuity equation.
 * @param {number} flatPct  Annual flat rate percentage (e.g. 12)
 * @param {number} n        Tenure in months
 * @returns {string}        Effective APR as a percentage string (e.g. "21.46")
 */
function effectiveAPR(flatPct, n) {
  const P   = 1;
  const I   = P * (flatPct / 100) * (n / 12);
  const emi = (P + I) / n;

  let r = (flatPct / 100) / 12;           // initial guess: flat monthly rate
  for (let i = 0; i < 500; i++) {
    const denom = r === 0 ? n : (1 - Math.pow(1 + r, -n)) / r;
    const fVal  = P - emi * denom;
    const pow1  = Math.pow(1 + r, -(n + 1));
    const pow2  = Math.pow(1 + r, -n);
    const dfVal = emi * (n * pow1 / r - (1 - pow2) / (r * r));
    const rNew  = r - fVal / dfVal;
    if (Math.abs(rNew - r) < 1e-10) { r = rNew; break; }
    r = rNew;
  }
  return (r * 12 * 100).toFixed(2);
}

/** Set a button into loading state and return a restore function. */
function btnLoading(btnId, loadingText) {
  const btn  = document.getElementById(btnId);
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `
    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
    </svg>
    <span>${loadingText}</span>`;
  return () => { btn.disabled = false; btn.innerHTML = orig; };
}


/* ═════════════════════════════ THEME MANAGER ══════════════════════ */
const ThemeManager = {
  isDark: true,

  init() {
    const saved = localStorage.getItem('ff-theme');
    this.isDark = saved !== null ? saved === 'dark' : true;
    this._apply();
    document.getElementById('themeToggle').addEventListener('click', () => this.toggle());
  },

  toggle() {
    this.isDark = !this.isDark;
    localStorage.setItem('ff-theme', this.isDark ? 'dark' : 'light');
    this._apply();
  },

  _apply() {
    document.documentElement.classList.toggle('dark', this.isDark);
    document.getElementById('themeIcon').textContent = this.isDark ? '☀️' : '🌙';
  },
};


/* ═════════════════════════════════ TOAST ══════════════════════════ */
const Toast = {
  _container: null,

  init() {
    this._container = document.getElementById('toastContainer');
  },

  show(message, type = 'info', duration = 4500) {
    const palettes = {
      success: { bg: 'dark:bg-emerald-900/95 bg-emerald-50', bd: 'dark:border-emerald-700 border-emerald-200', ic: 'text-emerald-500', tx: 'dark:text-emerald-50 text-emerald-800', icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>' },
      error:   { bg: 'dark:bg-red-900/95 bg-red-50',     bd: 'dark:border-red-700 border-red-200',     ic: 'text-red-500',     tx: 'dark:text-red-50 text-red-800',     icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/>' },
      warning: { bg: 'dark:bg-amber-900/95 bg-amber-50',  bd: 'dark:border-amber-700 border-amber-200', ic: 'text-amber-500',   tx: 'dark:text-amber-50 text-amber-800',  icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>' },
      info:    { bg: 'dark:bg-indigo-900/95 bg-indigo-50', bd: 'dark:border-indigo-700 border-indigo-200', ic: 'text-indigo-500', tx: 'dark:text-indigo-50 text-indigo-800', icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>' },
    };
    const p  = palettes[type] || palettes.info;
    const id = `t-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;

    const el = document.createElement('div');
    el.id        = id;
    el.className = `toast-item flex items-start gap-3 px-4 py-3 rounded-xl border shadow-2xl backdrop-blur-md ${p.bg} ${p.bd}`;
    el.innerHTML = `
      <svg class="w-5 h-5 ${p.ic} flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">${p.icon}</svg>
      <p class="text-sm font-medium ${p.tx} leading-relaxed flex-1">${message}</p>
      <button onclick="this.closest('[id]').remove()"
              class="${p.ic} opacity-50 hover:opacity-100 transition-opacity flex-shrink-0 mt-0.5">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>`;

    this._container.appendChild(el);

    if (duration > 0) {
      setTimeout(() => {
        el.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
        el.style.opacity    = '0';
        el.style.transform  = 'translateX(60px)';
        setTimeout(() => el.remove(), 380);
      }, duration);
    }
  },

  success: (m, d) => Toast.show(m, 'success', d),
  error:   (m, d) => Toast.show(m, 'error',   d),
  warning: (m, d) => Toast.show(m, 'warning', d),
  info:    (m, d) => Toast.show(m, 'info',    d),
};


/* ══════════════════════════════ TAB MANAGER ═══════════════════════ */
const TabManager = {
  _tabs: ['loan', 'otp', 'compliance'],

  init() { this.switch('loan'); },

  switch(name) {
    this._tabs.forEach(tab => {
      const btn   = document.getElementById(`tab-${tab}`);
      const panel = document.getElementById(`panel-${tab}`);
      const isActive = tab === name;

      // Tab button styling
      btn.classList.toggle('tab-active',   isActive);
      btn.classList.toggle('tab-inactive', !isActive);
      btn.classList.toggle('dark:text-indigo-400', isActive);
      btn.classList.toggle('text-indigo-600',      isActive);
      btn.classList.toggle('font-semibold',        isActive);
      btn.classList.toggle('dark:text-slate-400',  !isActive);
      btn.classList.toggle('text-slate-500',       !isActive);
      btn.classList.toggle('font-medium',          !isActive);

      // Panel visibility
      if (isActive) {
        panel.classList.remove('hidden');
        panel.classList.add('animate-slide-up');
        setTimeout(() => panel.classList.remove('animate-slide-up'), 500);
      } else {
        panel.classList.add('hidden');
      }
    });
  },
};


/* ═══════════════════════════════ API CLIENT ═══════════════════════ */
const API = {
  async post(path, body) {
    const res  = await fetch(path, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = json.detail || json.message || `HTTP ${res.status}`;
      const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      err.status = res.status;
      err.data   = json;
      throw err;
    }
    return json;
  },
};


/* ═══════════════════════════ LOAN CALCULATOR ══════════════════════ */
const LoanCalculator = {
  _activeTenure: 12,

  init() {
    // Sync sliders ↔ number inputs
    this._sync('principal',    'principalSlider');
    this._sync('annual_rate',  'rateSlider');

    // Debounced auto-calculate on any change
    const debouncedCalc = debounce(() => LoanCalculator.calculate(), 650);
    ['principal', 'principalSlider', 'annual_rate', 'rateSlider', 'tenure_months']
      .forEach(id => document.getElementById(id).addEventListener('input', debouncedCalc));

    // Highlight default 12M quick-select
    this._highlightTenureBtn(12);

    // Calculate once on load
    this.calculate();
  },

  _sync(inputId, sliderId) {
    const inp = document.getElementById(inputId);
    const sld = document.getElementById(sliderId);
    inp.addEventListener('input', () => { sld.value = inp.value; });
    sld.addEventListener('input', () => { inp.value = sld.value; });
  },

  setTenure(months) {
    document.getElementById('tenure_months').value = months;
    this._activeTenure = months;
    this._highlightTenureBtn(months);
    this.calculate();
  },

  _highlightTenureBtn(active) {
    document.querySelectorAll('.tenure-q').forEach(btn => {
      const m = parseInt(btn.textContent);
      if (m === active) {
        btn.className = 'tenure-q px-3 py-1 text-xs rounded-lg font-semibold transition-all dark:bg-indigo-600 bg-indigo-100 dark:text-white text-indigo-700';
      } else {
        btn.className = 'tenure-q px-3 py-1 text-xs rounded-lg font-semibold transition-all dark:bg-slate-800 bg-slate-100 dark:text-slate-400 text-slate-500 dark:hover:bg-slate-700 hover:bg-slate-200';
      }
    });
  },

  async calculate() {
    const principal     = parseFloat(document.getElementById('principal').value);
    const annual_rate   = parseFloat(document.getElementById('annual_rate').value);
    const tenure_months = parseInt(document.getElementById('tenure_months').value);

    if (!principal || !annual_rate || !tenure_months ||
        principal <= 0 || annual_rate <= 0 || tenure_months <= 0) return;

    const restore = btnLoading('calcBtn', 'Calculating…');

    try {
      const data = await API.post('/api/v1/loan/calculate', { principal, annual_rate, tenure_months });
      this._render(data);
      Toast.success('EMI calculated ✓', 3000);
    } catch (err) {
      Toast.error(`Calculation error: ${err.message}`);
    } finally {
      restore();
    }
  },

  _render(d) {
    // Show results
    document.getElementById('loanPlaceholder').classList.add('hidden');
    const res = document.getElementById('loanResults');
    res.classList.remove('hidden');
    res.classList.add('flex');

    // Metric cards
    document.getElementById('resInterest').textContent = fmtINR(d.total_interest);
    document.getElementById('resTotal').textContent    = fmtINR(d.total_payable);
    document.getElementById('resEMI').textContent      = fmtINR(d.monthly_emi);

    // Detail table
    document.getElementById('dtPrincipal').textContent = fmtINR(d.principal);
    document.getElementById('dtRate').textContent      = d.annual_rate + '%';
    document.getElementById('dtTenure').textContent    = d.tenure_months + ' months';
    document.getElementById('dtInterest').textContent  = fmtINR(d.total_interest);
    document.getElementById('dtPayable').textContent   = fmtINR(d.total_payable);

    // Visual breakdown bar
    const pVal = parseFloat(d.principal);
    const tVal = parseFloat(d.total_payable);
    const pPct = ((pVal / tVal) * 100).toFixed(1);
    document.getElementById('barPrincipal').style.width = pPct + '%';
    document.getElementById('barInterest').style.width  = (100 - parseFloat(pPct)).toFixed(1) + '%';

    // APR estimate
    const apr = effectiveAPR(parseFloat(d.annual_rate), d.tenure_months);
    document.getElementById('aprFlat').textContent = d.annual_rate + '%';
    document.getElementById('aprEff').textContent  = `~${apr}%`;
  },
};


/* ════════════════════════════ OTP WORKFLOW ═════════════════════════ */
const OTPWorkflow = {
  _refId:           null,
  _jwt:             null,
  _timerInterval:   null,
  _resendInterval:  null,
  _timerSecs:       180,
  _backoffSecs:     30,
  _resendCount:     0,

  init() {
    this._initOTPBoxes();
    document.getElementById('otpVerifyBtn').addEventListener('click', () => this.verify());
    document.getElementById('otpResendBtn').addEventListener('click', () => this.resend());
    document.getElementById('otpModalClose').addEventListener('click', () => this.closeModal());
    document.getElementById('otpBackdrop').addEventListener('click', () => this.closeModal());
    document.getElementById('phoneNumber').addEventListener('keydown', e => {
      if (e.key === 'Enter') this.sendOTP();
    });
  },

  _initOTPBoxes() {
    const boxes = document.querySelectorAll('.otp-box');
    boxes.forEach((box, i) => {
      // Input: accept only one digit, auto-advance
      box.addEventListener('input', e => {
        const v = e.target.value.replace(/\D/g, '');
        e.target.value = v ? v.slice(-1) : '';
        if (e.target.value) {
          e.target.classList.add('filled');
          if (i < 5) boxes[i + 1].focus();
          // Auto-submit when all filled
          if ([...boxes].every(b => b.value)) {
            setTimeout(() => this.verify(), 250);
          }
        } else {
          e.target.classList.remove('filled');
        }
      });

      // Keyboard navigation
      box.addEventListener('keydown', e => {
        if (e.key === 'Backspace' && !e.target.value && i > 0) {
          boxes[i - 1].value = '';
          boxes[i - 1].classList.remove('filled');
          boxes[i - 1].focus();
        }
        if (e.key === 'ArrowLeft'  && i > 0) boxes[i - 1].focus();
        if (e.key === 'ArrowRight' && i < 5) boxes[i + 1].focus();
      });

      // Paste: distribute digits across boxes
      box.addEventListener('paste', e => {
        e.preventDefault();
        const pasted = (e.clipboardData || window.clipboardData)
          .getData('text').replace(/\D/g, '').slice(0, 6);
        [...pasted].forEach((ch, j) => {
          if (boxes[j]) { boxes[j].value = ch; boxes[j].classList.add('filled'); }
        });
        const nextEmpty = [...boxes].findIndex(b => !b.value);
        (nextEmpty !== -1 ? boxes[nextEmpty] : boxes[5]).focus();
      });
    });
  },

  _getOTP()   { return [...document.querySelectorAll('.otp-box')].map(b => b.value).join(''); },
  _clearOTP() { document.querySelectorAll('.otp-box').forEach(b => { b.value = ''; b.classList.remove('filled', 'otp-error'); }); },
  _shakeOTP() {
    document.querySelectorAll('.otp-box').forEach(b => b.classList.add('otp-error'));
    setTimeout(() => document.querySelectorAll('.otp-box').forEach(b => b.classList.remove('otp-error')), 600);
  },

  async sendOTP() {
    const raw = document.getElementById('phoneNumber').value.trim().replace(/\D/g, '');
    if (raw.length !== 10) { Toast.error('Enter a valid 10-digit mobile number'); return; }

    const phone   = `+91${raw}`;
    const restore = btnLoading('sendOtpBtn', 'Sending…');

    try {
      const data = await API.post('/api/v1/otp/send', { phone_number: phone });
      this._refId         = data.reference_id;
      this._resendCount   = 0;
      this._backoffSecs   = 30;

      document.getElementById('otpPhoneDisplay').textContent = phone;
      this.openModal();
      this._startTimer(data.expires_in || 180);
      this._startResendCountdown(this._backoffSecs);
      this._setStep(2);

      Toast.success(`OTP sent to ${phone}`);
    } catch (err) {
      Toast.error(`Send failed: ${err.message}`);
    } finally {
      restore();
    }
  },

  async verify() {
    const otp = this._getOTP();
    if (otp.length !== 6) { Toast.warning('Enter all 6 digits'); return; }

    const phone   = `+91${document.getElementById('phoneNumber').value.trim().replace(/\D/g, '')}`;
    const btn     = document.getElementById('otpVerifyBtn');
    btn.disabled  = true;
    const origTxt = btn.textContent;
    btn.textContent = 'Verifying…';

    try {
      const data = await API.post('/api/v1/otp/verify', {
        phone_number: phone,
        otp,
        reference_id: this._refId,
      });
      this._jwt = data.access_token;
      this._stopTimer();
      this.closeModal();
      this._setStep(3);
      this._showSuccess(phone, data.access_token);
      Toast.success('Phone verified! JWT issued ✓');
    } catch (err) {
      this._shakeOTP();
      this._clearOTP();
      document.getElementById('otp0').focus();
      Toast.error(err.message);
    } finally {
      btn.disabled    = false;
      btn.textContent = origTxt;
    }
  },

  async resend() {
    const phone   = `+91${document.getElementById('phoneNumber').value.trim().replace(/\D/g, '')}`;
    const btn     = document.getElementById('otpResendBtn');
    btn.disabled  = true;

    try {
      const data = await API.post('/api/v1/otp/resend', {
        phone_number: phone,
        reference_id: this._refId,
      });
      this._refId       = data.reference_id;
      this._resendCount++;
      this._backoffSecs = data.retry_after || this._backoffSecs * 2;

      this._clearOTP();
      document.getElementById('otp0').focus();
      this._startTimer(data.expires_in || 180);
      this._startResendCountdown(this._backoffSecs);
      Toast.info(`OTP resent. Next resend in ${data.retry_after}s`);
    } catch (err) {
      Toast.error(`Resend failed: ${err.message}`);
      btn.disabled = false;
    }
  },

  openModal() {
    const m = document.getElementById('otpModal');
    m.classList.remove('hidden');
    m.classList.add('flex');
    this._clearOTP();
    setTimeout(() => document.getElementById('otp0').focus(), 120);
  },

  closeModal() {
    const m = document.getElementById('otpModal');
    m.classList.add('hidden');
    m.classList.remove('flex');
    this._stopTimer();
    clearInterval(this._resendInterval);
  },

  _startTimer(secs) {
    this._stopTimer();
    this._timerSecs = secs;
    const el = document.getElementById('otpTimer');

    const tick = () => {
      const m = Math.floor(this._timerSecs / 60);
      const s = this._timerSecs % 60;
      el.textContent = `${m}:${String(s).padStart(2, '0')}`;
      el.style.color = this._timerSecs <= 30 ? '#ef4444' : '';
      if (--this._timerSecs < 0) {
        this._stopTimer();
        el.textContent = 'Expired';
        Toast.warning('OTP expired — request a new one');
      }
    };
    tick();
    this._timerInterval = setInterval(tick, 1000);
  },

  _stopTimer() { clearInterval(this._timerInterval); },

  _startResendCountdown(secs) {
    clearInterval(this._resendInterval);
    const btn = document.getElementById('otpResendBtn');
    const cd  = document.getElementById('resendCountdown');
    btn.disabled = true;
    let rem = secs;

    const tick = () => {
      cd.textContent = rem > 0 ? `(${rem}s)` : '';
      if (rem-- <= 0) {
        clearInterval(this._resendInterval);
        btn.disabled = false;
      }
    };
    tick();
    this._resendInterval = setInterval(tick, 1000);
  },

  _setStep(step) {
    for (let i = 1; i <= 3; i++) {
      const ind = document.getElementById(`si${i}`);
      const lbl = document.getElementById(`sl${i}`);
      if (i < step) {
        ind.className = 'w-8 h-8 rounded-full bg-emerald-500 text-white text-sm font-bold flex items-center justify-center';
        ind.textContent = '✓';
        lbl.className   = 'text-sm font-semibold dark:text-emerald-400 text-emerald-600';
      } else if (i === step) {
        ind.className = 'w-8 h-8 rounded-full bg-indigo-600 text-white text-sm font-bold flex items-center justify-center';
        ind.textContent = String(i);
        lbl.className   = 'text-sm font-semibold dark:text-indigo-400 text-indigo-600';
      } else {
        ind.className = 'w-8 h-8 rounded-full dark:bg-slate-800 bg-slate-200 dark:text-slate-500 text-slate-400 text-sm font-bold flex items-center justify-center';
        ind.textContent = String(i);
        lbl.className   = 'text-sm font-medium dark:text-slate-500 text-slate-400';
      }
    }
  },

  _showSuccess(phone, token) {
    document.getElementById('otpPhoneCard').classList.add('hidden');
    const card = document.getElementById('otpSuccessCard');
    card.classList.remove('hidden');
    document.getElementById('verifiedPhone').textContent = phone;
    document.getElementById('jwtDisplay').textContent    = token.length > 80
      ? token.substring(0, 78) + '…'
      : token;
    this._jwt = token;
  },

  copyToken() {
    if (!this._jwt) return;
    navigator.clipboard.writeText(this._jwt)
      .then(() => Toast.success('JWT token copied to clipboard ✓'))
      .catch(() => Toast.error('Clipboard access denied'));
  },

  reset() {
    document.getElementById('otpPhoneCard').classList.remove('hidden');
    document.getElementById('otpSuccessCard').classList.add('hidden');
    document.getElementById('phoneNumber').value = '';
    this._jwt = null; this._refId = null;
    this._setStep(1);
  },
};


/* ══════════════════════════ COMPLIANCE WORKFLOW ════════════════════ */
const ComplianceWorkflow = {
  _links:     [],
  _kfsOpen:   false,

  init() {
    // Pre-populate 4 example audit links so the hard gate is satisfied by default
    [
      'https://audit.example.com/doc/kfs-signed',
      'https://audit.example.com/doc/fpc-disclosure',
      'https://audit.example.com/doc/borrower-consent',
      'https://audit.example.com/doc/credit-check',
    ].forEach(u => this.addLink(u));
  },

  addLink(value = '') {
    this._links.push(value);
    this._renderLinks();
    this._updateGate();
  },

  removeLink(idx) {
    this._links.splice(idx, 1);
    this._renderLinks();
    this._updateGate();
  },

  _renderLinks() {
    const box = document.getElementById('auditLinksBox');
    box.innerHTML = '';
    this._links.forEach((val, i) => {
      const div = document.createElement('div');
      div.className = 'flex items-center gap-2 animate-fade-in';
      div.innerHTML = `
        <span class="w-5 h-5 rounded-full dark:bg-slate-700 bg-slate-200 flex items-center justify-center
                     text-xs font-extrabold dark:text-slate-400 text-slate-500 flex-shrink-0">${i + 1}</span>
        <input type="text" value="${val.replace(/"/g, '&quot;')}"
               placeholder="https://audit.example.com/doc/..."
               class="flex-1 px-2.5 py-1.5 text-xs dark:bg-slate-800 bg-slate-50
                      dark:border-slate-700 border-slate-200 border rounded-lg
                      dark:text-white text-slate-900
                      focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
               oninput="ComplianceWorkflow._links[${i}] = this.value; ComplianceWorkflow._updateGate()">
        <button onclick="ComplianceWorkflow.removeLink(${i})"
                class="w-6 h-6 rounded-lg flex items-center justify-center text-sm flex-shrink-0
                       dark:bg-slate-700 bg-slate-200 dark:text-slate-400 text-slate-500
                       dark:hover:bg-red-900/60 hover:bg-red-100 dark:hover:text-red-400 hover:text-red-500 transition-all">×</button>`;
      box.appendChild(div);
    });
  },

  _updateGate() {
    const validCount = this._links.filter(l => l.trim().length > 0).length;
    const dot  = document.getElementById('gateDot');
    const cnt  = document.getElementById('gateCount');
    const warn = document.getElementById('gateWarn');
    const ok   = document.getElementById('gateOK');

    cnt.textContent = `${validCount}/4`;
    const passed = validCount >= 4;
    dot.className  = `w-1.5 h-1.5 rounded-full ${passed ? 'bg-emerald-500' : 'bg-red-500'}`;
    warn.classList.toggle('hidden', passed);
    ok.classList.toggle('hidden', !passed);
  },

  async verify() {
    const loanId  = document.getElementById('cLoanId').value.trim();
    const name    = document.getElementById('cBorrower').value.trim();
    const prin    = parseFloat(document.getElementById('cPrincipal').value);
    const rate    = parseFloat(document.getElementById('cRate').value);
    const tenure  = parseInt(document.getElementById('cTenure').value);
    const links   = this._links.filter(l => l.trim());

    if (!loanId || !name || !prin || !rate || !tenure) {
      Toast.error('Please fill all required fields');
      return;
    }
    if (links.length === 0) {
      Toast.warning('Add at least one audit evidence link');
      return;
    }

    const restore = btnLoading('compBtn', 'Verifying…');

    try {
      const data = await API.post('/api/v1/compliance/verify', {
        loan_id:       loanId,
        borrower_name: name,
        principal:     prin,
        annual_rate:   rate,
        tenure_months: tenure,
        audit_links:   links,
      });
      this._renderResults(data);
      Toast.success(
        data.approved ? 'Compliance APPROVED ✓' : 'Compliance gate failed — check results',
        5000
      );
    } catch (err) {
      Toast.error(`Compliance error: ${err.message}`);
    } finally {
      restore();
    }
  },

  _renderResults(d) {
    document.getElementById('compPlaceholder').classList.add('hidden');
    const res = document.getElementById('compResults');
    res.classList.remove('hidden');
    res.classList.add('flex');

    // ── Approval banner ──────────────────────────────────────────
    const banner = document.getElementById('approvalBanner');
    const icon   = document.getElementById('approvalIcon');
    const title  = document.getElementById('approvalTitle');
    const badge  = document.getElementById('approvalBadge');
    const reason = document.getElementById('approvalReason');

    if (d.approved) {
      banner.className = 'rounded-2xl p-5 border dark:bg-emerald-500/10 bg-emerald-50 dark:border-emerald-500/20 border-emerald-200 flex items-start gap-4 animate-slide-up';
      icon.className   = 'w-12 h-12 rounded-xl bg-emerald-500/20 flex items-center justify-center flex-shrink-0';
      icon.innerHTML   = '<svg class="w-7 h-7 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>';
      title.textContent = 'Compliance APPROVED';
      title.className   = 'font-extrabold text-lg dark:text-emerald-400 text-emerald-600';
      badge.textContent = '✓ GATE PASSED';
      badge.className   = 'px-2.5 py-0.5 rounded-full text-xs font-extrabold bg-emerald-500 text-white';
      reason.className  = 'text-sm dark:text-emerald-300 text-emerald-700 leading-relaxed opacity-80';
    } else {
      banner.className = 'rounded-2xl p-5 border dark:bg-red-500/10 bg-red-50 dark:border-red-500/20 border-red-200 flex items-start gap-4 animate-slide-up';
      icon.className   = 'w-12 h-12 rounded-xl bg-red-500/20 flex items-center justify-center flex-shrink-0';
      icon.innerHTML   = '<svg class="w-7 h-7 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>';
      title.textContent = 'Compliance BLOCKED';
      title.className   = 'font-extrabold text-lg dark:text-red-400 text-red-600';
      badge.textContent = '🔒 GATE FAILED';
      badge.className   = 'px-2.5 py-0.5 rounded-full text-xs font-extrabold bg-red-500 text-white';
      reason.className  = 'text-sm dark:text-red-300 text-red-700 leading-relaxed opacity-80';
    }
    reason.textContent = d.reason;

    // ── Delivery tracker ─────────────────────────────────────────
    this._renderDelivery(d.delivery_status);

    // ── KFS document ─────────────────────────────────────────────
    this._renderKFS(d.kfs);

    // ── Audit trail ──────────────────────────────────────────────
    this._renderAuditTrail(d.audit_trail_entry, d.audit_trail_id, d.audit_links_received);
  },

  _renderDelivery(status) {
    const order = { sent: 0, delivered: 1, read: 2 };
    const idx   = order[status] ?? 0;

    [[1,'ds1','dc1'], [2,'ds2','dc2'], [3,'ds3',null]].forEach(([n, dsId, dcId]) => {
      const stepEl = document.getElementById(dsId);
      const done   = (n - 1) <= idx;

      stepEl.style.background   = done ? '#10b981' : '';
      stepEl.style.borderColor  = done ? '#10b981' : '#334155';
      stepEl.style.boxShadow    = done ? '0 0 0 4px rgba(16,185,129,0.2)' : '';
      const svg = stepEl.querySelector('svg');
      if (svg) svg.style.color = done ? 'white' : '';

      if (dcId) {
        const conn = document.getElementById(dcId);
        conn.classList.toggle('done', (n - 1) < idx);
      }
    });
  },

  _renderKFS(kfs) {
    if (!kfs) return;
    document.getElementById('kfsDocLabel').textContent = kfs.document_id || 'KFS Document';

    const rows = [
      ['Document ID',      kfs.document_id || '—'],
      ['Generated At',     kfs.generated_at ? new Date(kfs.generated_at).toLocaleString('en-IN') : '—'],
      ['Loan ID',          kfs.loan_id || '—'],
      ['Borrower Name',    kfs.borrower_name || '—'],
      ['Principal',        kfs.principal_inr ? '₹' + parseFloat(kfs.principal_inr).toLocaleString('en-IN', {minimumFractionDigits:2}) : '—'],
      ['Annual Rate',      kfs.annual_interest_rate_pct ? kfs.annual_interest_rate_pct + '%' : '—'],
      ['Tenure',           kfs.tenure_months ? kfs.tenure_months + ' months' : '—'],
      ['Monthly EMI',      kfs.monthly_emi_inr ? '₹' + parseFloat(kfs.monthly_emi_inr).toLocaleString('en-IN', {minimumFractionDigits:2}) : '—'],
      ['Total Interest',   kfs.total_interest_inr ? '₹' + parseFloat(kfs.total_interest_inr).toLocaleString('en-IN', {minimumFractionDigits:2}) : '—'],
      ['Total Payable',    kfs.total_payable_inr ? '₹' + parseFloat(kfs.total_payable_inr).toLocaleString('en-IN', {minimumFractionDigits:2}) : '—'],
      ['Digital Signature', kfs.digital_signature ? kfs.digital_signature.slice(0, 22) + '…' : '—'],
    ];

    document.getElementById('kfsFields').innerHTML = rows.map(([k, v]) => `
      <div class="flex justify-between items-start gap-4 py-2 dark:border-b dark:border-slate-800 border-b border-slate-100 last:border-0">
        <span class="text-xs dark:text-slate-500 text-slate-400 flex-shrink-0">${k}</span>
        <span class="text-xs font-semibold dark:text-white text-slate-900 text-right break-all">${v}</span>
      </div>`).join('');

    // APR breakdown
    const flatRate = parseFloat(kfs.annual_interest_rate_pct || 12);
    const tenure   = kfs.tenure_months || 12;
    document.getElementById('kfsFlat').textContent = flatRate + '%';
    document.getElementById('kfsAPR').textContent  = `~${effectiveAPR(flatRate, tenure)}%`;
  },

  _renderAuditTrail(entry, trailId, linksReceived) {
    if (!entry) return;
    const rows = [
      ['Trail ID',         trailId || entry.trail_id || '—'],
      ['Event',            entry.event || '—'],
      ['Actor',            entry.actor || '—'],
      ['Timestamp (UTC)',  entry.timestamp_iso ? new Date(entry.timestamp_iso).toLocaleString('en-IN') : '—'],
      ['Payload Hash',     entry.payload_hash ? entry.payload_hash.slice(0, 26) + '…' : '—'],
      ['Retention Until',  entry.retention_until ? new Date(entry.retention_until).getFullYear() + ' (15-year archive)' : '—'],
      ['Audit Links Filed',`${linksReceived || 0} evidence link(s)`],
    ];

    document.getElementById('auditTrailFields').innerHTML = rows.map(([k, v]) => `
      <div class="flex justify-between items-start gap-4 py-2 dark:border-b dark:border-slate-800 border-b border-slate-100 last:border-0">
        <span class="text-xs dark:text-slate-500 text-slate-400 flex-shrink-0">${k}</span>
        <span class="text-xs font-mono font-semibold dark:text-emerald-400 text-emerald-600 text-right break-all">${v}</span>
      </div>`).join('');
  },

  toggleKFS() {
    this._kfsOpen = !this._kfsOpen;
    document.getElementById('kfsBody').classList.toggle('hidden', !this._kfsOpen);
    document.getElementById('kfsChevron').style.transform = this._kfsOpen ? 'rotate(180deg)' : '';
  },
};


/* ══════════════════════════════════ INIT ═══════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  ThemeManager.init();
  Toast.init();
  TabManager.init();
  LoanCalculator.init();
  OTPWorkflow.init();
  ComplianceWorkflow.init();
});
