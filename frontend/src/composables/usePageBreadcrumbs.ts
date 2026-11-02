import { onScopeDispose, shallowReactive, type ComputedRef, type InjectionKey } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

export interface PageBreadcrumb {
  label: string
  to?: RouteLocationRaw
  action?: () => void | Promise<void>
  beforeNavigate?: () => void
}

type BreadcrumbLayer = {
  items: () => PageBreadcrumb[]
  append: boolean
  close?: () => void
}

const layers = shallowReactive(new Map<symbol, BreadcrumbLayer>())
export const pageBreadcrumbsKey: InjectionKey<ComputedRef<PageBreadcrumb[]>> = Symbol('page-breadcrumbs')

/** Register local page or drawer navigation, removed with its component scope. */
export function usePageBreadcrumbs(items: () => PageBreadcrumb[], options: { append?: boolean; close?: () => void } = {}) {
  const key = Symbol('breadcrumb-layer')
  layers.set(key, { items, append: options.append ?? false, close: options.close })
  onScopeDispose(() => layers.delete(key))
}

export function resolvePageBreadcrumbs(base: PageBreadcrumb[]): PageBreadcrumb[] {
  const active = [...layers.values()].filter(layer => layer.items().length)
  const wrap = (items: PageBreadcrumb[], owner: number) => items.map(item => ({
    ...item,
    beforeNavigate: () => {
      // Returning to a parent also dismisses any deeper drawer, including when
      // the parent is an internal page state rather than a different URL.
      for (const layer of active.slice(owner + 1).reverse()) {
        if (layer.append) layer.close?.()
      }
      item.beforeNavigate?.()
    },
  }))
  let result = wrap(base, -1)
  active.forEach((layer, index) => {
    const items = wrap(layer.items(), index)
    result = layer.append ? [...result, ...items] : items
  })
  return result
}
