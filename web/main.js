import axios from 'axios'

const tg = window.Telegram?.WebApp
if (tg) {
  tg.ready()
  tg.expand()
}

const root = document.getElementById('app')
const state = { me: null, loading: false, error: null, deliveries: [], theme: 'light' }

function applyTelegramTheme() {
  const bgColor = tg?.themeParams?.bg_color || '#f6f9fc'
  const textColor = tg?.themeParams?.text_color || '#0f172a'
  const isDark = (tg?.colorScheme || '').toLowerCase() === 'dark'
  state.theme = isDark ? 'dark' : 'light'
  document.documentElement.setAttribute('data-theme', state.theme)
  document.body.style.background = bgColor
  document.body.style.color = textColor
}

applyTelegramTheme()
tg?.onEvent?.('themeChanged', applyTelegramTheme)

function setLoading(v) { state.loading = v; render() }
function setError(e) { state.error = e; render() }

async function callApi(method, url, data) {
  const base = import.meta.env.VITE_API_BASE || ''
  const initData = tg?.initData || new URLSearchParams(location.search).get('init_data') || ''
  const headers = { 'X-Telegram-Init-Data': initData }
  const res = await axios({ method, url: base + url, headers, data })
  return res.data
}

async function loadMe() {
  try {
    setLoading(true)
    state.me = await callApi('get', '/api/me')
    const d = await callApi('get', '/api/deliveries')
    state.deliveries = d?.items || []
    setError(null)
  } catch (e) {
    setError(e?.response?.data?.detail || 'Ошибка загрузки')
  } finally {
    setLoading(false)
  }
}

// Modal helpers
function openModal(id) { document.getElementById(id)?.classList.add('open') }
function closeModal(id) { document.getElementById(id)?.classList.remove('open') }

async function addTrack(form) {
  const track = (form.querySelector('#trackInput')?.value || '').trim()
  const delivery = (form.querySelector('#deliverySelect')?.value || '').trim()
  if (!track) { setError('Введите трек-код'); return }
  try {
    setLoading(true)
    await callApi('post', '/api/track', { track, delivery })
    await loadMe()
    closeModal('modalAddTrack')
  } catch (e) {
    setError(e?.response?.data?.detail || 'Ошибка добавления')
  } finally {
    setLoading(false)
  }
}

async function clearTracks() {
  try {
    setLoading(true)
    await callApi('delete', '/api/tracks')
    await loadMe()
  } catch (e) {
    setError(e?.response?.data?.detail || 'Ошибка очистки')
  } finally {
    setLoading(false)
  }
}

async function showAddress() {
  try {
    setLoading(true)
    const res = await callApi('get', '/api/address')
    const el = document.getElementById('addressText')
    if (el) el.innerText = (res?.text || '').replace(/<[^>]*>?/gm, '')
    openModal('modalAddress')
  } catch (e) {
    setError(e?.response?.data?.detail || 'Не удалось получить адрес')
  } finally {
    setLoading(false)
  }
}

async function contactManager(form) {
  const text = (form.querySelector('#managerText')?.value || '').trim()
  try {
    setLoading(true)
    const res = await callApi('post', '/api/manager', { text })
    if (res?.ok) closeModal('modalManager')
  } catch (e) {
    setError(e?.response?.data?.detail || 'Не удалось отправить запрос')
  } finally {
    setLoading(false)
  }
}

async function buyRequest(form) {
  const text = (form.querySelector('#buyText')?.value || '').trim()
  if (!text) { setError('Опишите заказ'); return }
  try {
    setLoading(true)
    const res = await callApi('post', '/api/buy', { text })
    if (res?.ok) closeModal('modalBuy')
  } catch (e) {
    setError(e?.response?.data?.detail || 'Не удалось отправить запрос')
  } finally {
    setLoading(false)
  }
}

function renderTracks(tracks) {
  if (!tracks?.length) return '<div class="banner">Пока нет зарегистрированных трек-кодов</div>'
  return `
    <div class="list">
      <div class="list-title">Ваши трек-коды</div>
      ${tracks.map(t => `
        <div class="track">
          <div class="track-left">
            <span class="track-code"><code>${t.track}</code></span>
            ${t.delivery ? `<span class="chip">${t.delivery}</span>` : ''}
          </div>
          <div class="track-actions">
            <button class="btn" data-photo-track="${t.track}">Фото</button>
          </div>
        </div>
      `).join('')}
    </div>
  `
}

async function openPhotos(track) {
  try {
    setLoading(true)
    const data = await callApi('get', `/api/track/${encodeURIComponent(track)}/photos`)
    const wrap = document.getElementById('photosWrap')
    if (wrap) {
      const list = (data?.photos || [])
      if (!list.length) {
        wrap.innerHTML = '<div class="banner">Фото пока нет</div>'
      } else {
        wrap.innerHTML = '<div class="list-title">Фото</div>' + list.map(p => `
          <img alt="photo" src="/api/tg_photo/${encodeURIComponent(p)}" style="max-width:100%; border-radius: 12px; border:1px solid var(--color-border); margin-bottom:12px" />
        `).join('')
      }
    }
    openModal('modalPhotos')
  } catch (e) {
    setError(e?.response?.data?.detail || 'Не удалось загрузить фото')
  } finally {
    setLoading(false)
  }
}

function render() {
  const { me, loading, error } = state
  root.innerHTML = `
    <div class="app" data-theme="${state.theme}">
      <div class="container">
        <div class="header">
          <div>
            <h1 class="title">Probuy</h1>
            <div class="subtitle">Мини‑приложение</div>
          </div>
        </div>

        ${loading ? '<div class="loading">Загрузка…</div>' : ''}
        ${error ? `<div class="error">${error}</div>` : ''}

        ${me ? `
          <div class="card code-card">
            <div>
              <div class="subtitle">Ваш код клиента</div>
              <div class="code">${me.code}</div>
            </div>
            <div class="actions">
              <button class="btn" id="btnAddr">Адрес склада</button>
              <button class="btn primary" id="btnMgr">Менеджер</button>
            </div>
          </div>

          ${renderTracks(me.tracks)}

          <div class="actions" style="margin-top: 16px">
            <button class="btn" id="btnAdd">Добавить трек</button>
            <button class="btn" id="btnClr">Очистить</button>
            <button class="btn success" id="btnBuy">Оформить заказ</button>
          </div>
        ` : ''}
      </div>
    </div>

    <!-- Modals -->
    <div class="modal-overlay" id="modalAddress">
      <div class="modal">
        <h3 class="modal-title">Адрес склада</h3>
        <div id="addressText" class="banner">Загрузка…</div>
        <div class="modal-actions">
          <button class="btn" data-close="modalAddress">Закрыть</button>
        </div>
      </div>
    </div>

    <div class="modal-overlay" id="modalAddTrack">
      <div class="modal">
        <h3 class="modal-title">Добавить трек</h3>
        <form id="formAddTrack">
          <div class="field">
            <label class="label" for="trackInput">Трек-код</label>
            <input class="input" id="trackInput" placeholder="A1B2C3D4..." />
          </div>
          <div class="field">
            <label class="label" for="deliverySelect">Тип доставки</label>
            <select class="select" id="deliverySelect">
              <option value="">Не выбрано</option>
              ${state.deliveries.map(d => `<option value="${d.key}">${d.name}</option>`).join('')}
            </select>
          </div>
          <div class="modal-actions">
            <button type="button" class="btn" data-close="modalAddTrack">Отмена</button>
            <button type="submit" class="btn primary">Добавить</button>
          </div>
        </form>
      </div>
    </div>

    <div class="modal-overlay" id="modalManager">
      <div class="modal">
        <h3 class="modal-title">Связаться с менеджером</h3>
        <form id="formManager">
          <div class="field">
            <label class="label" for="managerText">Сообщение (необязательно)</label>
            <textarea class="textarea" id="managerText" placeholder="Коротко опишите вопрос"></textarea>
          </div>
          <div class="modal-actions">
            <button type="button" class="btn" data-close="modalManager">Отмена</button>
            <button type="submit" class="btn primary">Отправить</button>
          </div>
        </form>
      </div>
    </div>

    <div class="modal-overlay" id="modalBuy">
      <div class="modal">
        <h3 class="modal-title">Оформить заказ</h3>
        <form id="formBuy">
          <div class="field">
            <label class="label" for="buyText">Что купить и в каком количестве?</label>
            <textarea class="textarea" id="buyText" placeholder="Например: 10 шт. товара X, цвет синий"></textarea>
          </div>
          <div class="modal-actions">
            <button type="button" class="btn" data-close="modalBuy">Отмена</button>
            <button type="submit" class="btn success">Отправить</button>
          </div>
        </form>
      </div>
    </div>

    <div class="modal-overlay" id="modalPhotos">
      <div class="modal">
        <h3 class="modal-title">Фото по треку</h3>
        <div id="photosWrap" class="banner">Загрузка…</div>
        <div class="modal-actions">
          <button class="btn" data-close="modalPhotos">Закрыть</button>
        </div>
      </div>
    </div>
  `

  document.getElementById('btnAdd')?.addEventListener('click', () => openModal('modalAddTrack'))
  document.getElementById('btnClr')?.addEventListener('click', clearTracks)
  document.getElementById('btnAddr')?.addEventListener('click', showAddress)
  document.getElementById('btnMgr')?.addEventListener('click', () => openModal('modalManager'))
  document.getElementById('btnBuy')?.addEventListener('click', () => openModal('modalBuy'))

  document.querySelectorAll('[data-close]')?.forEach(btn => btn.addEventListener('click', (e) => {
    const id = e.currentTarget.getAttribute('data-close')
    closeModal(id)
  }))

  document.getElementById('formAddTrack')?.addEventListener('submit', (e) => {
    e.preventDefault(); addTrack(e.currentTarget)
  })
  document.getElementById('formManager')?.addEventListener('submit', (e) => {
    e.preventDefault(); contactManager(e.currentTarget)
  })
  document.getElementById('formBuy')?.addEventListener('submit', (e) => {
    e.preventDefault(); buyRequest(e.currentTarget)
  })

  document.querySelectorAll('[data-photo-track]')?.forEach(btn => btn.addEventListener('click', (e) => {
    const track = e.currentTarget.getAttribute('data-photo-track')
    openPhotos(track)
  }))
}

render()
loadMe()
