import { api } from './api'
import type { AccountOption } from './types'
import './styles/manual-confirm-enhancer.css'

const tooltipId = 'manual-confirm-field-tooltip'
let tooltip: HTMLDivElement | null = null
let tooltipTarget: HTMLElement | null = null
let observer: MutationObserver | null = null
let scheduled = false
let accountRequest: Promise<AccountOption[]> | null = null
let accountCatalog: AccountOption[] = []

function normalized(value: string | null | undefined) {
  return (value ?? '').trim().toLocaleLowerCase()
}

function ensureAccounts() {
  if (accountCatalog.length) return Promise.resolve(accountCatalog)
  if (!accountRequest) {
    accountRequest = api.accounts(1000, true)
      .then(rows => {
        accountCatalog = rows
        return rows
      })
      .catch(() => [])
  }
  return accountRequest
}

function getTooltip() {
  if (tooltip) return tooltip
  tooltip = document.createElement('div')
  tooltip.id = tooltipId
  tooltip.className = 'manual-confirm-field-tooltip'
  tooltip.setAttribute('role', 'tooltip')
  tooltip.hidden = true
  document.body.appendChild(tooltip)
  return tooltip
}

function hideTooltip() {
  if (!tooltip) return
  tooltip.hidden = true
  tooltipTarget?.removeAttribute('aria-describedby')
  tooltipTarget = null
}

function showTooltip(target: HTMLElement) {
  const text = target.dataset.confirmHint?.trim()
  if (!text || target.scrollWidth <= target.clientWidth) {
    hideTooltip()
    return
  }
  const bubble = getTooltip()
  bubble.textContent = text
  bubble.hidden = false
  tooltipTarget?.removeAttribute('aria-describedby')
  tooltipTarget = target
  target.setAttribute('aria-describedby', tooltipId)

  const anchor = target.getBoundingClientRect()
  const box = bubble.getBoundingClientRect()
  const left = Math.max(12, Math.min(anchor.left, window.innerWidth - box.width - 12))
  const below = anchor.bottom + 8
  const top = below + box.height <= window.innerHeight - 12
    ? below
    : Math.max(12, anchor.top - box.height - 8)
  bubble.style.left = `${left}px`
  bubble.style.top = `${top}px`
}

function bindHint(target: HTMLElement, text: string, extraClass = '') {
  target.className = `manual-confirm-hint ${extraClass}`.trim()
  target.textContent = text || '—'
  target.dataset.confirmHint = text || '—'
  target.tabIndex = 0
  target.setAttribute('aria-label', text || '—')
  target.onmouseenter = () => showTooltip(target)
  target.onmouseleave = hideTooltip
  target.onfocus = () => showTooltip(target)
  target.onblur = hideTooltip
}

function renderHintCell(cell: HTMLTableCellElement, text: string, extraClass = '') {
  const existing = cell.querySelector<HTMLElement>('.manual-confirm-hint')
  if (existing && existing.textContent === (text || '—')) return
  const value = document.createElement('span')
  bindHint(value, text, extraClass)
  cell.replaceChildren(value)
}

function accountMaps() {
  const byUm = new Map<string, AccountOption>()
  const names = new Map<string, AccountOption[]>()
  for (const account of accountCatalog) {
    const um = normalized(account.um_no)
    if (um && !byUm.has(um)) byUm.set(um, account)
    const name = normalized(account.account_name)
    if (!name) continue
    const rows = names.get(name)
    if (rows) rows.push(account)
    else names.set(name, [account])
  }
  return { byUm, names }
}

function enhanceAccountTable(table: HTMLTableElement) {
  const headers = table.querySelectorAll<HTMLTableCellElement>('thead th')
  if (headers.length >= 3) {
    if (headers[0].textContent !== '账号昵称') headers[0].textContent = '账号昵称'
    if (headers[1].textContent !== '账号ID') headers[1].textContent = '账号ID'
    if (headers[2].textContent !== '账号类型') headers[2].textContent = '账号类型'
  }

  const cols = table.querySelectorAll<HTMLTableColElement>('colgroup col')
  if (cols.length >= 3) {
    cols[0].style.width = '42%'
    cols[1].style.width = '35%'
    cols[2].style.width = '23%'
  }

  const { byUm, names } = accountMaps()
  table.querySelectorAll<HTMLTableRowElement>('tbody tr').forEach(row => {
    const cells = row.querySelectorAll<HTMLTableCellElement>('td')
    if (cells.length < 3) return
    const name = cells[0].textContent?.trim() || ''
    const previousUm = row.dataset.manualConfirmUm || cells[1].textContent?.trim() || ''
    if (!row.dataset.manualConfirmUm && previousUm && previousUm !== '—') row.dataset.manualConfirmUm = previousUm

    let account = row.dataset.manualConfirmAccountId
      ? accountCatalog.find(item => item.account_id === row.dataset.manualConfirmAccountId)
      : undefined
    if (!account) account = byUm.get(normalized(previousUm))
    if (!account) {
      const sameName = names.get(normalized(name)) || []
      if (sameName.length === 1) account = sameName[0]
    }
    if (!account) return

    row.dataset.manualConfirmAccountId = account.account_id
    renderHintCell(cells[1], account.account_id, 'identifier')
  })
}

function enhanceTopicTable(table: HTMLTableElement) {
  const headers = table.querySelectorAll<HTMLTableCellElement>('thead th')
  if (headers.length >= 4) {
    if (headers[0].textContent !== '内容类型') headers[0].textContent = '内容类型'
    if (headers[1].textContent !== '选题标题') headers[1].textContent = '选题标题'
    if (headers[2].textContent !== '选题大纲') headers[2].textContent = '选题大纲'
    headers[3].style.display = 'none'
  }

  const cols = table.querySelectorAll<HTMLTableColElement>('colgroup col')
  if (cols.length >= 4) {
    cols[0].style.width = '24%'
    cols[1].style.width = '32%'
    cols[2].style.width = '44%'
    cols[3].style.display = 'none'
  }

  table.querySelectorAll<HTMLTableRowElement>('tbody tr').forEach(row => {
    const cells = row.querySelectorAll<HTMLTableCellElement>('td')
    if (cells.length < 4) return
    const contentType = row.dataset.manualConfirmContentType
      || cells[3].textContent?.trim()
      || '—'
    row.dataset.manualConfirmContentType = contentType
    renderHintCell(cells[0], contentType)
    cells[3].style.display = 'none'
  })
}

function enhance() {
  document.querySelectorAll<HTMLTableElement>('.manual-submit-account-table').forEach(enhanceAccountTable)
  document.querySelectorAll<HTMLTableElement>('.manual-submit-topic-table').forEach(enhanceTopicTable)
}

function scheduleEnhance() {
  if (scheduled) return
  scheduled = true
  requestAnimationFrame(() => {
    scheduled = false
    enhance()
  })
}

export function installManualConfirmEnhancer() {
  void ensureAccounts().then(scheduleEnhance)
  scheduleEnhance()
  observer?.disconnect()
  observer = new MutationObserver(scheduleEnhance)
  observer.observe(document.body, { childList: true, subtree: true, characterData: true })
  window.addEventListener('scroll', hideTooltip, true)
  window.addEventListener('resize', hideTooltip)
}
