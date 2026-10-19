let installed = false

export function installTopicDetailClickFix() {
  if (installed) return
  installed = true

  document.addEventListener('click', event => {
    if (!(event.target instanceof Element)) return
    const title = event.target.closest('.account-week-plan-card h3')
    if (!title) return
    const card = title.closest<HTMLElement>('.account-week-plan-card')
    if (!card) return

    event.stopPropagation()
    card.click()
  }, true)
}
