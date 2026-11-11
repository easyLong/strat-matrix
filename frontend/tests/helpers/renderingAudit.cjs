// Select ordinary text on neutral surfaces for screenshot pixel checks.
// Avoid semantic colours, tinted tags, occluded pages and text outside the viewport.
async function neutralTextSamples(page, viewportOnly = false) {
  return page.evaluate(viewportOnly => {
    const samples = []
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    let node
    while ((node = walker.nextNode()) && samples.length < 24) {
      const text = node.textContent.trim(), parent = node.parentElement
      if (!parent || !/[\u4e00-\u9fff]{2}/.test(text) || parent.closest('script,style,option,svg')) continue
      const style = getComputedStyle(parent), colour = style.color.match(/[\d.]+/g)?.map(Number)
      if (!colour || colour[0] !== colour[1] || colour[1] !== colour[2] || style.visibility !== 'visible') continue
      const range = document.createRange(); range.selectNodeContents(node)
      const rect = range.getBoundingClientRect()
      if (rect.width < 12 || rect.width > 380 || rect.height < 8 || rect.height > 28 || rect.x < 0 || rect.y < 0 || rect.right > innerWidth || rect.bottom > innerHeight) continue
      const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2)
      if (!hit || !(hit === parent || parent.contains(hit))) continue
      let neutral = true
      for (let ancestor = parent; ancestor; ancestor = ancestor.parentElement) {
        const background = getComputedStyle(ancestor).backgroundColor.match(/[\d.]+/g)?.map(Number)
        if (!background || background[3] === 0) continue
        if (background[0] !== background[1] || background[1] !== background[2]) { neutral = false; break }
        if (background.length === 3 || background[3] === 1) break
      }
      if (!neutral) continue
      samples.push({text, colour: style.color, x: rect.x + (viewportOnly ? 0 : scrollX), y: rect.y + (viewportOnly ? 0 : scrollY), width: rect.width, height: rect.height})
    }
    return samples
  }, viewportOnly)
}

module.exports = { neutralTextSamples }
