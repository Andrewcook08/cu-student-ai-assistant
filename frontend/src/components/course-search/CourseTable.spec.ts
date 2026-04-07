import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CourseTable from './CourseTable.vue'
import type { Course } from '@/types/index'

const sampleCourses: Course[] = [
  {
    code: 'CSCI 1300',
    title: 'Computer Science 1',
    credits: '3',
    dept: 'CSCI',
    instruction_mode: 'In Person',
    sections: [{ crn: '10001', meets: 'MWF 9-10', instructor: 'Smith', status: 'Open' }],
  },
  {
    code: 'CSCI 2270',
    title: 'Data Structures',
    credits: '3',
    dept: 'CSCI',
    instruction_mode: 'In Person',
    sections: [{ crn: '10002', meets: 'TTh 11-12', instructor: 'Jones', status: 'Full' }],
  },
]

describe('CourseTable', () => {
  it('renders a row for each course it is given', () => {
    const wrapper = mount(CourseTable, { props: { courses: sampleCourses } })
    expect(wrapper.text()).toContain('CSCI 1300')
    expect(wrapper.text()).toContain('CSCI 2270')
    expect(wrapper.findAll('tbody tr').length).toBe(sampleCourses.length)
  })

  it('shows the empty state when given no courses', () => {
    const wrapper = mount(CourseTable, { props: { courses: [] } })
    expect(wrapper.find('.empty-state').exists()).toBe(true)
    expect(wrapper.findAll('tbody tr').length).toBe(0)
  })

  it('does not filter its input — it renders everything passed in', () => {
    const mixed: Course[] = [
      ...sampleCourses,
      { code: 'MATH 1300', title: 'Calculus 1', credits: '4', dept: 'MATH', sections: [] },
    ]
    const wrapper = mount(CourseTable, { props: { courses: mixed } })
    expect(wrapper.text()).toContain('CSCI 1300')
    expect(wrapper.text()).toContain('CSCI 2270')
    expect(wrapper.text()).toContain('MATH 1300')
  })

  it('expands a row when clicked and collapses it on second click', async () => {
    const wrapper = mount(CourseTable, { props: { courses: sampleCourses } })
    const firstRow = wrapper.findAll('tbody tr.course-row')[0]
    await firstRow.trigger('click')
    expect(wrapper.findAll('tr.course-row--expanded').length).toBe(1)
    await firstRow.trigger('click')
    expect(wrapper.findAll('tr.course-row--expanded').length).toBe(0)
  })
})
