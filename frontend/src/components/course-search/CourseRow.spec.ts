import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CourseRow from './CourseRow.vue'
import type { Course } from '@/types/index'

function makeCourse(overrides: Partial<Course> = {}): Course {
  return {
    code: 'CSCI 1300',
    title: 'Intro CS',
    credits: '3',
    dept: 'CSCI',
    instruction_mode: 'In Person',
    sections: [],
    ...overrides,
  }
}

function mountRow(course: Course) {
  // CourseRow renders a <tr>; wrap in a table so the DOM is valid.
  return mount(
    {
      components: { CourseRow },
      props: ['course'],
      template: '<table><tbody><CourseRow :course="course" :is-expanded="false" /></tbody></table>',
    },
    { props: { course } },
  )
}

describe('CourseRow status chip', () => {
  it('renders Open status with the open class', () => {
    const wrapper = mountRow(makeCourse({ status: 'Open' }))
    const chip = wrapper.find('.status-chip')
    expect(chip.text()).toBe('Open')
    expect(chip.classes()).toContain('open')
  })

  it('renders Waitlist status with the waitlist class', () => {
    const wrapper = mountRow(makeCourse({ status: 'Waitlist' }))
    const chip = wrapper.find('.status-chip')
    expect(chip.text()).toBe('Waitlist')
    expect(chip.classes()).toContain('waitlist')
  })

  it('renders Closed status with the closed class', () => {
    const wrapper = mountRow(makeCourse({ status: 'Closed' }))
    const chip = wrapper.find('.status-chip')
    expect(chip.text()).toBe('Closed')
    expect(chip.classes()).toContain('closed')
  })

  it('falls back to an em-dash (not "Unknown") when status is missing', () => {
    const wrapper = mountRow(makeCourse({ status: undefined }))
    const chip = wrapper.find('.status-chip')
    expect(chip.text()).toBe('—')
    expect(chip.text()).not.toContain('Unknown')
    expect(chip.classes()).toContain('unknown')
  })
})
