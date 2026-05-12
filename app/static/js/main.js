/* pechepro front-end glue (plan-1).
 * Responsibilities:
 * - Populate species/water/region dropdowns from /api/* endpoints.
 * - Wire the GPS button to navigator.geolocation.
 * - Submit /conditions form with lat/lon/region.
 * Plan-2 services power the actual data; plan-1 only orchestrates fetch.
 */
(function () {
  'use strict';

  function fetchJson(url, opts) {
    return fetch(url, opts || {}).then(function (r) {
      if (!r.ok) {
        throw new Error('HTTP ' + r.status + ' ' + url);
      }
      return r.json();
    });
  }

  function el(id) { return document.getElementById(id); }

  function populateSelect(selectEl, items, valueKey, labelKeys) {
    if (!selectEl) return;
    selectEl.innerHTML = '';
    var placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.disabled = true;
    placeholder.selected = true;
    placeholder.textContent = '— Select —';
    selectEl.appendChild(placeholder);
    items.forEach(function (item) {
      var opt = document.createElement('option');
      opt.value = item[valueKey];
      var labels = labelKeys.map(function (k) { return item[k]; }).filter(Boolean);
      opt.textContent = labels.join(' / ');
      selectEl.appendChild(opt);
    });
  }

  function setStatus(msg, kind) {
    var s = el('form-status');
    if (!s) return;
    s.textContent = msg || '';
    s.dataset.kind = kind || '';
  }

  function loadDropdowns() {
    var lang = (document.documentElement.lang || 'en').slice(0, 2);
    var nameKey = lang === 'fr' ? 'name_fr' : 'name_en';
    var commonKey = lang === 'fr' ? 'common_name_fr' : 'common_name_en';

    if (el('species')) {
      fetchJson('/api/species').then(function (rows) {
        populateSelect(el('species'), rows, 'id', [commonKey]);
      }).catch(function (e) { setStatus(e.message, 'error'); });
    }

    if (el('water')) {
      fetchJson('/api/water-types').then(function (rows) {
        populateSelect(el('water'), rows, 'id', [nameKey]);
      }).catch(function (e) { setStatus(e.message, 'error'); });
    }

    if (el('region')) {
      fetchJson('/api/regions').then(function (rows) {
        populateSelect(el('region'), rows, 'id', [nameKey, 'iso_code']);
        var none = document.createElement('option');
        none.value = '';
        none.textContent = '— —';
        var first = el('region').firstChild;
        el('region').insertBefore(none, first && first.nextSibling ? first.nextSibling : null);
      }).catch(function (e) { setStatus(e.message, 'error'); });
    }

    if (el('filter-species')) {
      fetchJson('/api/species').then(function (rows) {
        populateSelect(el('filter-species'), rows, 'id', [commonKey]);
      }).catch(function () { /* silent — page still usable */ });
    }
  }

  function bindGps() {
    var btn = el('use-gps');
    if (!btn || !navigator.geolocation) return;
    btn.addEventListener('click', function () {
      setStatus('Locating…', 'info');
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          el('lat').value = pos.coords.latitude.toFixed(4);
          el('lon').value = pos.coords.longitude.toFixed(4);
          setStatus('Located: ' + el('lat').value + ', ' + el('lon').value, 'ok');
        },
        function (err) {
          setStatus('GPS denied: ' + (err && err.message ? err.message : 'unknown'), 'error');
        },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 }
      );
    });
  }

  function bindLangToggle() {
    var link = el('lang-toggle');
    if (!link) return;
    link.addEventListener('click', function (ev) {
      ev.preventDefault();
      var nextLang = link.dataset.lang;
      var u = new URL(window.location.href);
      u.searchParams.set('lang', nextLang);
      window.location.href = u.toString();
    });
  }

  function bindFormSubmit() {
    var form = el('recommend-form');
    if (!form) return;
    form.addEventListener('submit', function () {
      // Native submit; lat/lon may be blank (region-only mode).
    });
  }

  // Expose for testing.
  window.pechepro = window.pechepro || {};
  window.pechepro.fetchJson = fetchJson;
  window.pechepro.el = el;
  window.pechepro.setStatus = setStatus;

  function init() {
    loadDropdowns();
    bindGps();
    bindLangToggle();
    bindFormSubmit();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
