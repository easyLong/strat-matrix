import type { AccountOption } from '../types'

export interface AccountImportRow {
  rowNumber: number
  umNo: string
  accountId: string
  reason: string
}

export interface AccountImportResult {
  totalRows: number
  identifiedIds: string[]
  selectedIds: string[]
  duplicates: AccountImportRow[]
  unmatched: AccountImportRow[]
  planned: AccountImportRow[]
}

function csvRows(text: string) {
  const rows: { cells: string[]; line: number }[] = []
  let cells: string[] = []
  let cell = ''
  let quoted = false
  let line = 1
  let rowStart = 1
  for (let index = 0; index < text.length; index++) {
    const char = text[index]
    if (char === '"') {
      if (quoted && text[index + 1] === '"') { cell += '"'; index++ }
      else quoted = !quoted
    } else if (char === ',' && !quoted) {
      cells.push(cell.trim()); cell = ''
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && text[index + 1] === '\n') index++
      line++
      if (quoted) cell += '\n'
      else {
        cells.push(cell.trim()); cell = ''
        if (cells.some(value => value !== '')) rows.push({ cells, line: rowStart })
        cells = []
        rowStart = line
      }
    } else cell += char
  }
  if (quoted) throw new Error(`第 ${rowStart} 行的 CSV 引号未闭合，请检查文件`)
  cells.push(cell.trim())
  if (cells.some(value => value !== '')) rows.push({ cells, line: rowStart })
  return rows
}

export function recognizeAccountImport(
  text: string,
  accounts: AccountOption[],
  plannedAccountIds: ReadonlySet<string>,
): AccountImportResult {
  const rows = csvRows(text.replace(/^\uFEFF/, ''))
  if (!rows.length) throw new Error('模板中没有账号数据，请填写 UM 号或账号 ID')
  const normalize = (value: string) => value.trim().toLocaleLowerCase()
  const headers = rows[0].cells.map(value => normalize(value).replace(/[\s_-]/g, ''))
  const umColumn = headers.findIndex(value => ['um号', '属主um号', 'umno', 'umnumber'].includes(value))
  const idColumn = headers.findIndex(value => ['账号id', 'accountid'].includes(value))
  const hasHeader = umColumn >= 0 || idColumn >= 0
  const data = rows.slice(hasHeader ? 1 : 0)
  if (!data.length) throw new Error('模板只有表头，请填写账号数据')
  if (data.length > 1000) throw new Error('每次最多导入 1000 行账号数据')

  const byId = new Map(accounts.map(account => [normalize(account.account_id), account]))
  const byUm = new Map<string, AccountOption[]>()
  for (const account of accounts) {
    const umNo = normalize(account.um_no || '')
    if (umNo) byUm.set(umNo, [...(byUm.get(umNo) || []), account])
  }
  const result: AccountImportResult = { totalRows: data.length, identifiedIds: [], selectedIds: [], duplicates: [], unmatched: [], planned: [] }
  const seen = new Set<string>()
  for (const row of data) {
    const umNo = (row.cells[hasHeader ? umColumn : 0] || '').trim()
    const accountId = (row.cells[hasHeader ? idColumn : 1] || '').trim()
    const issue: AccountImportRow = { rowNumber: row.line, umNo, accountId, reason: '' }
    let matches = accountId ? [byId.get(normalize(accountId))].filter((account): account is AccountOption => !!account) : byUm.get(normalize(umNo)) || []
    // A one-column file without a header may contain either identifier.
    if (!hasHeader && !accountId && !matches.length && byId.has(normalize(umNo))) matches = [byId.get(normalize(umNo))!]
    if (accountId && umNo) matches = matches.filter(account => normalize(account.um_no || '') === normalize(umNo))
    if (matches.length !== 1) {
      issue.reason = matches.length > 1 ? 'UM 号对应多个账号，请补充账号 ID' : !umNo && !accountId ? '未填写 UM 号或账号 ID' : accountId && umNo ? '账号未识别或 UM 号与账号 ID 不对应' : '未能识别账号'
      result.unmatched.push(issue)
      continue
    }
    const account = matches[0]
    if (seen.has(account.account_id)) {
      result.duplicates.push({ ...issue, reason: '账号重复，仅保留首次记录' })
      continue
    }
    seen.add(account.account_id)
    result.identifiedIds.push(account.account_id)
    if (plannedAccountIds.has(account.account_id)) result.planned.push({ ...issue, reason: '所选投放日期已完成人工策划' })
    else result.selectedIds.push(account.account_id)
  }
  return result
}
