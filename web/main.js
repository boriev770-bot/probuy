import axios from 'axios'

const tg = window.Telegram?.WebApp
if (tg) {
  tg.ready()
  tg.expand()
}

const root = document.getElementById('app')
const state = { me: null, loading: false, error: null }

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
    setError(null)
  } catch (e) {
    setError(e?.response?.data?.detail || 'Ошибка загрузки')
  } finally {
    setLoading(false)
  }
}

async function addTrack() {
  const track = prompt('Введите трек-код (A-Z0-9, 8-40 символов)')
  if (!track) return
  try {
    setLoading(true)
    await callApi('post', '/api/track', { track })
    await loadMe()
  } catch (e) {
    setError(e?.response?.data?.detail || 'Ошибка добавления')
  } finally {
    setLoading(false)
  }
}

async function clearTracks() {
  if (!confirm('Очистить историю треков?')) return
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

function render() {
  const { me, loading, error } = state
  root.innerHTML = `
    <div style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; padding: 12px; color: ${tg?.themeParams?.text_color || '#111'}; background: ${tg?.themeParams?.bg_color || '#fff'}; min-height: 100vh;">
      <h2 style="margin: 0 0 12px">Probuy Mini App</h2>
      ${loading ? '<div>Загрузка…</div>' : ''}
      ${error ? `<div style="color: #c00">${error}</div>` : ''}
      ${me ? `
        <div style="margin: 8px 0">Код клиента: <b>${me.code}</b></div>
        <div style="margin: 8px 0">Треки:</div>
        <ul>
          ${me.tracks.map(t => `<li><code>${t.track}</code> ${t.delivery ? '('+t.delivery+')' : ''}</li>`).join('') || '<i>Пока пусто</i>'}
        </ul>
        <div style="display:flex; gap: 8px; margin-top: 12px">
          <button id="btnAdd" style="padding:8px 12px">Добавить трек</button>
          <button id="btnClr" style="padding:8px 12px">Очистить</button>
        </div>
      ` : ''}
    </div>
  `
  document.getElementById('btnAdd')?.addEventListener('click', addTrack)
  document.getElementById('btnClr')?.addEventListener('click', clearTracks)
}

render()
loadMe()
