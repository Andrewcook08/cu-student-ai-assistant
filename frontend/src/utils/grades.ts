// Standard CU Boulder letter grades. F has no +/- variants.
export const GRADE_OPTIONS = [
  'A',
  'A-',
  'B+',
  'B',
  'B-',
  'C+',
  'C',
  'C-',
  'D+',
  'D',
  'D-',
  'F',
] as const

export type Grade = (typeof GRADE_OPTIONS)[number]
