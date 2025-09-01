import axios from 'axios'

const tg = window.Telegram?.WebApp
if (tg) {
  tg.ready()
  tg.expand()
}

const root = document.getElementById('app')
const state = { me: null, loading: false, error: null, deliveries: [] }

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

async function addTrack() {
  const track = prompt('Введите трек-код (A-Z0-9, 8-40 символов)')
  if (!track) return
  const delivery = state.deliveries.length
    ? prompt('Тип доставки: ' + state.deliveries.map(d => `${d.key} = ${d.name}`).join(', ') + '\nОставьте пустым, если не важно')
    : ''
  try {
    setLoading(true)
    await callApi('post', '/api/track', { track, delivery: (delivery||'').trim() })
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
        <div style="margin: 8px 0"><button id="btnAddr" style="padding:6px 10px">Показать адрес склада</button></div>
        <div style="margin: 8px 0">Треки:</div>
        <ul>
          ${me.tracks.map(t => `<li><code>${t.track}</code> ${t.delivery ? '('+t.delivery+')' : ''}</li>`).join('') || '<i>Пока пусто</i>'}
        </ul>
        <div style="display:flex; gap: 8px; margin-top: 12px">
          <button id="btnAdd" style="padding:8px 12px">Добавить трек</button>
          <button id="btnClr" style="padding:8px 12px">Очистить</button>
          <button id="btnMgr" style="padding:8px 12px; background:#2b74e4; color:#fff">Связаться с менеджером</button>
        </div>
        <div style="margin-top:12px">
          <button id="btnBuy" style="padding:8px 12px; background:#24a148; color:#fff">Оформить заказ</button>
        </div>
      ` : ''}
    </div>
  `
  document.getElementById('btnAdd')?.addEventListener('click', addTrack)
  document.getElementById('btnClr')?.addEventListener('click', clearTracks)
  document.getElementById('btnAddr')?.addEventListener('click', async () => {
    try {
      setLoading(true)
      const res = await callApi('get', '/api/address')
      alert(res?.text || 'Адрес недоступен')
    } catch (e) {
      setError(e?.response?.data?.detail || 'Не удалось получить адрес')
    } finally {
      setLoading(false)
    }
  })
  document.getElementById('btnMgr')?.addEventListener('click', async () => {
    const text = prompt('Коротко опишите вопрос для менеджера (необязательно)') || ''
    try {
      setLoading(true)
      const res = await callApi('post', '/api/manager', { text })
      if (res?.ok) alert('Запрос отправлен менеджеру')
    } catch (e) {
      setError(e?.response?.data?.detail || 'Не удалось отправить запрос')
    } finally {
      setLoading(false)
    }
  })
  document.getElementById('btnBuy')?.addEventListener('click', async () => {
    const text = prompt('Что купить и в каком количестве?') || ''
    if (!text.trim()) return
    try {
      setLoading(true)
      const res = await callApi('post', '/api/buy', { text })
      if (res?.ok) alert('Запрос отправлен менеджеру')
    } catch (e) {
      setError(e?.response?.data?.detail || 'Не удалось отправить запрос')
    } finally {
      setLoading(false)
    }
  })
}

render()
loadMe()
