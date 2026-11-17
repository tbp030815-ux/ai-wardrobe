import { describe, expect, it } from 'vitest'
import { safeNextPath } from './nextUrl'

const ORIGIN = 'http://localhost:5173'

describe('safeNextPath', () => {
  it('returns a same-origin path with its query and hash', () => {
    expect(safeNextPath('?next=%2Fuploads%2Fa.jpg%3Fx%3D1%23y', ORIGIN)).toBe(
      '/uploads/a.jpg?x=1#y',
    )
  })

  it('accepts an absolute URL that points at the same origin', () => {
    expect(
      safeNextPath(`?next=${encodeURIComponent(`${ORIGIN}/uploads/a.jpg`)}`, ORIGIN),
    ).toBe('/uploads/a.jpg')
  })

  it('returns null when next is missing', () => {
    expect(safeNextPath('', ORIGIN)).toBeNull()
    expect(safeNextPath('?foo=1', ORIGIN)).toBeNull()
  })

  it('rejects an absolute URL on another origin', () => {
    expect(safeNextPath('?next=https%3A%2F%2Fevil.com%2Fsteal', ORIGIN)).toBeNull()
  })

  it('rejects a protocol-relative URL', () => {
    expect(safeNextPath('?next=%2F%2Fevil.com%2Fsteal', ORIGIN)).toBeNull()
  })

  it('rejects non-http(s) schemes', () => {
    expect(safeNextPath('?next=javascript%3Aalert(1)', ORIGIN)).toBeNull()
  })

  it('rejects a malformed value', () => {
    expect(safeNextPath('?next=http%3A%2F%2F%5B', ORIGIN)).toBeNull()
  })
})
