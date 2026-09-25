import { describe, expect, it } from 'vitest'
import { parseIdsParam } from './tryonIds'

describe('parseIdsParam', () => {
  it('parses a plain list', () => {
    expect(parseIdsParam('3,4')).toEqual([3, 4])
  })

  it('returns an empty list when the param is absent', () => {
    expect(parseIdsParam(null)).toEqual([])
  })

  it('returns an empty list when the param is empty', () => {
    expect(parseIdsParam('')).toEqual([])
  })

  it('drops values that are not numbers', () => {
    expect(parseIdsParam('abc')).toEqual([])
  })

  it('keeps the good ids when some are garbage', () => {
    expect(parseIdsParam('3,abc,4')).toEqual([3, 4])
  })

  it('skips empty segments from doubled commas', () => {
    expect(parseIdsParam('3,,4')).toEqual([3, 4])
  })

  it('drops the repeated id', () => {
    expect(parseIdsParam('3,3')).toEqual([3])
  })

  it('drops negative ids', () => {
    expect(parseIdsParam('-1')).toEqual([])
  })

  it('drops zero — ids start at 1', () => {
    expect(parseIdsParam('0')).toEqual([])
  })

  it('drops non-integers', () => {
    expect(parseIdsParam('3.5')).toEqual([])
  })

  it('tolerates surrounding whitespace', () => {
    expect(parseIdsParam(' 3 , 4 ')).toEqual([3, 4])
  })

  it('preserves the order it was given', () => {
    expect(parseIdsParam('9,2,5')).toEqual([9, 2, 5])
  })
})
