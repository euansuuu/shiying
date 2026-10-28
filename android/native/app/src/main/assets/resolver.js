(() => {
  const jobId = __JOB_ID__;
  const initialId = __EXPECTED_ID__;
  if (window.__shiyingJob === jobId && window.__shiyingRead) return window.__shiyingRead();
  window.__shiyingJob = jobId;
  let latest = null;
  const targetId = () => initialId || window.__shiyingTargetId || (location.pathname.match(/^\/(?:video|note)\/([0-9]+)\/?$/) || [])[1] || '';
  const urls = value => Array.isArray(value) ? value.filter(item => typeof item === 'string' && item.length < 8193) : [];
  function normalized(item) {
    const video = item.video || {};
    const rates = video.bit_rate || video.bitRate;
    const addresses = [video.play_addr_h264 || video.playAddrH264,
      ...(Array.isArray(rates) ? rates.map(rate => rate?.play_addr || rate?.playAddr) : []),
      video.play_addr || video.playAddr, video.play_addr_265 || video.playAddr265];
    const playback = addresses.flatMap(address => urls(Array.isArray(address)
      ? address.map(value => typeof value === 'string' ? value : value?.src)
      : address?.url_list || address?.urlList));
    return {
      aweme_id: String(item.aweme_id || item.awemeId || ''), desc: typeof item.desc === 'string' ? item.desc : '',
      author: {nickname: item.author?.nickname || item.authorInfo?.nickname || ''}, aweme_type: item.aweme_type ?? item.awemeType,
      ...(item.music ? {music: {present: true}} : {}),
      video: {play_addr: {url_list: [...new Set(playback)]}},
      ...(Array.isArray(item.images) ? {images: item.images.map(image => ({
        uri: String(image?.uri || image?.image_id || image?.imageId || ''),
        url_list: urls(image?.url_list || image?.urlList), ...(image?.video && typeof image.video === 'object' && Object.keys(image.video).length ? {video: {present: true}} : {})
      }))} : {})
    };
  }
  function find(payload) {
    const expected = targetId();
    if (!expected) return null;
    const stack = [payload], seen = new Set();
    let count = 0;
    while (stack.length && count++ < 15000) {
      const node = stack.pop();
      if (!node || typeof node !== 'object' || seen.has(node)) continue;
      seen.add(node);
      if (String(node.aweme_id || node.awemeId || '') === expected && ('images' in node || 'video' in node)) {
        const candidate = normalized(node);
        const album = candidate.aweme_type === 68 || candidate.images?.length > 0 || location.pathname.startsWith('/note/');
        if (album ? candidate.images?.some(image => image.url_list.length) : candidate.video.play_addr.url_list.length) return candidate;
      }
      for (const value of Object.values(node)) if (value && typeof value === 'object') stack.push(value);
    }
    return null;
  }
  function inspect(payload) {
    const candidate = find(payload);
    if (!candidate) return null;
    latest = candidate;
    try {
      const message = JSON.stringify({jobId, detail: candidate});
      if (message.length <= 2000000 && window.ShiyingResult) window.ShiyingResult.postMessage(message);
    } catch (_) {}
    return candidate;
  }
  function allowed(url) {
    try {
      const value = new URL(url, location.href);
      return value.protocol === 'https:' && ['www.douyin.com', 'douyin.com'].includes(value.hostname) && /^\/aweme\/v1\/web\/aweme\/(?:detail|post)\/?$/.test(value.pathname);
    } catch (_) { return false; }
  }
  if (typeof window.fetch === 'function') {
    const original = window.fetch;
    window.fetch = function (...args) {
      const promise = original.apply(this, args);
      promise.then(response => {
        if (response.status === 200 && allowed(response.url)) response.clone().text().then(text => { if (text.length <= 2000000) inspect(JSON.parse(text)); }).catch(() => {});
      }).catch(() => {});
      return promise;
    };
  }
  if (window.XMLHttpRequest) {
    const open = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (...args) {
      this.addEventListener('load', () => {
        try {
          if (this.status !== 200 || !allowed(this.responseURL)) return;
          if (this.responseType === 'json') inspect(this.response);
          else if ((!this.responseType || this.responseType === 'text') && this.responseText.length <= 2000000) inspect(JSON.parse(this.responseText));
        } catch (_) {}
      }, {once: true});
      return open.apply(this, args);
    };
  }
  window.__shiyingBlockReason = function () {
    if (!document.querySelectorAll) return '';
    for (const element of document.querySelectorAll('[role="dialog"],[aria-modal="true"],[class*="captcha_verify"],#captcha_container')) {
      if (!element.getClientRects().length || getComputedStyle(element).visibility === 'hidden' || getComputedStyle(element).display === 'none') continue;
      const text = element.innerText || '';
      if (/验证码|安全验证|请完成验证|拖动滑块/.test(text)) return 'verification';
      if (/请先登录|登录后(?:才能|才可|继续)(?:观看|查看|访问)|登录后观看/.test(text)) return 'login';
    }
    return '';
  };
  window.__shiyingRead = function () {
    if (latest && latest.aweme_id === targetId()) return latest;
    for (const id of ['__UNIVERSAL_DATA_FOR_REHYDRATION__', 'RENDER_DATA']) {
      const text = document.getElementById(id)?.textContent || '';
      if (!text || text.length > 2000000) continue;
      try { const match = inspect(JSON.parse(id === 'RENDER_DATA' ? decodeURIComponent(text) : text)); if (match) return match; } catch (_) {}
    }
    for (const name of ['SSR_RENDER_DATA', '__INITIAL_STATE__', '_ROUTER_DATA']) {
      const match = inspect(window[name]);
      if (match) return match;
    }
    if (Array.isArray(window.__pace_f)) {
      let stream = '';
      for (const chunk of window.__pace_f) {
        if (!Array.isArray(chunk) || chunk[0] !== 1 || typeof chunk[1] !== 'string') continue;
        if (stream.length + chunk[1].length > 2000000) { stream = ''; break; }
        stream += chunk[1];
      }
      const bytes = new TextEncoder().encode(stream), decoder = new TextDecoder();
      let offset = 0;
      while (offset < bytes.length) {
        if (bytes[offset] === 10) { offset++; continue; }
        let separator = offset;
        while (separator < Math.min(bytes.length, offset + 32) && bytes[separator] !== 58) separator++;
        if (bytes[separator] !== 58 || !/^[0-9a-f]+$/i.test(decoder.decode(bytes.subarray(offset, separator)))) break;
        let end = separator + 1;
        // Flight text records use a UTF-8 byte count and can contain newlines or fake record headers.
        if (bytes[end] === 84) {
          let comma = end + 1;
          while (comma < Math.min(bytes.length, end + 10) && bytes[comma] !== 44) comma++;
          const length = decoder.decode(bytes.subarray(end + 1, comma));
          if (bytes[comma] !== 44 || !/^[0-9a-f]{1,8}$/i.test(length)) break;
          const next = comma + 1 + parseInt(length, 16);
          if (next > bytes.length) break;
          offset = next;
          continue;
        }
        while (end < bytes.length && bytes[end] !== 10) end++;
        const row = decoder.decode(bytes.subarray(separator + 1, end));
        offset = end + 1;
        try {
          const match = inspect(JSON.parse(row));
          if (match) return match;
        } catch (_) {}
      }
    }
    return null;
  };
  return window.__shiyingRead();
})();
