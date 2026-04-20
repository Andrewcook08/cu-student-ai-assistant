import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import RegisterModal from './RegisterModal.vue'
import * as authApi from '@/services/authApi'
import { GRADE_OPTIONS } from '@/utils/grades'

const VALID_PW = 'a-valid-pw-123'

function mountModal() {
  return mount(RegisterModal, {
    global: { plugins: [createPinia()] },
  })
}

async function fillValidStep1(wrapper: ReturnType<typeof mountModal>) {
  await wrapper.find('input[name="name"]').setValue('Alice')
  await wrapper.find('input[type="email"]').setValue('a@b.com')
  await wrapper.find('input#reg-password').setValue(VALID_PW)
  await wrapper.find('input#reg-confirm-password').setValue(VALID_PW)
}

beforeEach(() => {
  vi.restoreAllMocks()
  sessionStorage.clear()
})

describe('RegisterModal', () => {
  it('renders step 1 with name, email, password, confirm-password fields', () => {
    const wrapper = mountModal()
    expect(wrapper.find('input[name="name"]').exists()).toBe(true)
    expect(wrapper.find('input[type="email"]').exists()).toBe(true)
    expect(wrapper.find('input#reg-password').exists()).toBe(true)
    expect(wrapper.find('input#reg-confirm-password').exists()).toBe(true)
    expect(wrapper.text()).toContain('Create Account')
  })

  it('password field has autocomplete="new-password"', () => {
    const wrapper = mountModal()
    expect(wrapper.find('input#reg-password').attributes('autocomplete')).toBe('new-password')
  })

  it('disables submit on mount (empty fields)', () => {
    const wrapper = mountModal()
    expect(wrapper.find('[data-testid="submit-btn"]').attributes('disabled')).toBeDefined()
  })

  it('keeps submit disabled with password under 12 chars', async () => {
    const wrapper = mountModal()
    await wrapper.find('input[name="name"]').setValue('Alice')
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    await wrapper.find('input#reg-password').setValue('short')
    await wrapper.find('input#reg-confirm-password').setValue('short')
    expect(wrapper.find('[data-testid="submit-btn"]').attributes('disabled')).toBeDefined()
  })

  it('keeps submit disabled when confirm password does not match', async () => {
    const wrapper = mountModal()
    await wrapper.find('input[name="name"]').setValue('Alice')
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    await wrapper.find('input#reg-password').setValue(VALID_PW)
    await wrapper.find('input#reg-confirm-password').setValue('different-pw-12')
    expect(wrapper.find('[data-testid="submit-btn"]').attributes('disabled')).toBeDefined()
  })

  it('enables submit when all fields are valid + matching', async () => {
    const wrapper = mountModal()
    await fillValidStep1(wrapper)
    expect(wrapper.find('[data-testid="submit-btn"]').attributes('disabled')).toBeUndefined()
  })

  it('shows confirm-password error after blur on mismatch', async () => {
    const wrapper = mountModal()
    await wrapper.find('input#reg-password').setValue(VALID_PW)
    const confirm = wrapper.find('input#reg-confirm-password')
    await confirm.setValue('different-pw-12')
    await confirm.trigger('blur')
    expect(wrapper.find('[data-testid="confirm-password-error"]').exists()).toBe(true)
  })

  it('does not run the network request when step-1 fields are invalid', async () => {
    const registerSpy = vi.spyOn(authApi, 'register').mockResolvedValue({ token: 'x', user_id: 1 })
    const wrapper = mountModal()
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(registerSpy).not.toHaveBeenCalled()
  })

  it('shows password strength indicator when password is non-empty', async () => {
    const wrapper = mountModal()
    await wrapper.find('input#reg-password').setValue('short')
    expect(wrapper.find('[data-testid="password-strength"]').exists()).toBe(true)
  })

  it('emits close when Cancel button is clicked', async () => {
    const wrapper = mountModal()
    await wrapper.find('[data-testid="cancel-btn"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('shows server error as plain text (never innerHTML) when registration fails', async () => {
    vi.spyOn(authApi, 'register').mockRejectedValue(new Error('<script>alert(1)</script>'))
    const wrapper = mountModal()
    await fillValidStep1(wrapper)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const errorEl = wrapper.find('[data-testid="error-msg"]')
    expect(errorEl.exists()).toBe(true)
    expect(errorEl.element.textContent).toContain('<script>')
    expect(wrapper.find('script').exists()).toBe(false)
  })

  it('advances to step 2 even when fetchPrograms fails after successful registration', async () => {
    vi.spyOn(authApi, 'register').mockResolvedValue({ token: 'tok', user_id: 1 })
    vi.spyOn(authApi, 'fetchPrograms').mockRejectedValue(new Error('Network error'))
    const wrapper = mountModal()
    await fillValidStep1(wrapper)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('select[name="program"]').exists()).toBe(true)
  })

  it('moves to step 2 after successful registration and shows program dropdown', async () => {
    vi.spyOn(authApi, 'register').mockResolvedValue({ token: 'tok', user_id: 1 })
    vi.spyOn(authApi, 'fetchPrograms').mockResolvedValue([
      { id: 1, name: 'Computer Science BS', type: 'major', total_credits: 120 },
    ])
    const wrapper = mountModal()
    await fillValidStep1(wrapper)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('select[name="program"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Computer Science BS')
  })

  it('emits close after clicking Finish on step 2', async () => {
    vi.spyOn(authApi, 'register').mockResolvedValue({ token: 'tok', user_id: 1 })
    vi.spyOn(authApi, 'fetchPrograms').mockResolvedValue([
      { id: 1, name: 'CS BS', type: 'major', total_credits: 120 },
    ])
    vi.spyOn(authApi, 'updateCompletedCourses').mockResolvedValue(undefined)
    const wrapper = mountModal()
    await fillValidStep1(wrapper)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    await wrapper.find('[data-testid="finish-btn"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  describe('step 2 grade dropdown', () => {
    async function advanceToStep2() {
      vi.spyOn(authApi, 'register').mockResolvedValue({ token: 'tok', user_id: 1 })
      vi.spyOn(authApi, 'fetchPrograms').mockResolvedValue([
        { id: 1, name: 'CS BS', type: 'major', total_credits: 120 },
      ])
      vi.spyOn(authApi, 'fetchProgramRequirements').mockResolvedValue({
        program: { id: 1, name: 'CS BS', type: 'major' },
        requirements: [
          {
            id: 10,
            program_id: 1,
            sort_order: 0,
            requirement_type: 'course',
            course_code: 'CSCI1300',
            description: 'CS 1',
          },
        ],
      })
      vi.spyOn(authApi, 'updateProgram').mockResolvedValue(undefined)
      const wrapper = mountModal()
      await fillValidStep1(wrapper)
      await wrapper.find('form').trigger('submit')
      await flushPromises()
      // Pick program → triggers requirements load
      await wrapper.find('select[name="program"]').setValue('1')
      await flushPromises()
      // Tick the course checkbox so the grade select renders
      await wrapper.find('input[type="checkbox"]').setValue(true)
      return wrapper
    }

    it('renders a select (not a text input) with all 12 grade options plus "No grade"', async () => {
      const wrapper = await advanceToStep2()
      const select = wrapper.find('[data-testid="grade-select-CSCI1300"]')
      expect(select.exists()).toBe(true)
      expect(select.element.tagName).toBe('SELECT')
      const values = select.findAll('option').map((o) => (o.element as HTMLOptionElement).value)
      expect(values).toEqual(['', ...GRADE_OPTIONS])
    })

    it('F has no +/- variants', async () => {
      const wrapper = await advanceToStep2()
      const values = wrapper
        .find('[data-testid="grade-select-CSCI1300"]')
        .findAll('option')
        .map((o) => (o.element as HTMLOptionElement).value)
      expect(values).not.toContain('F+')
      expect(values).not.toContain('F-')
    })

    it('submits the chosen grade in the payload', async () => {
      const updateSpy = vi.spyOn(authApi, 'updateCompletedCourses').mockResolvedValue(undefined)
      const wrapper = await advanceToStep2()
      await wrapper.find('[data-testid="grade-select-CSCI1300"]').setValue('B+')
      await wrapper.find('[data-testid="finish-btn"]').trigger('click')
      await flushPromises()
      expect(updateSpy).toHaveBeenCalledWith([{ course_code: 'CSCI1300', grade: 'B+' }])
    })

    it('omits the grade key when "No grade" is selected', async () => {
      const updateSpy = vi.spyOn(authApi, 'updateCompletedCourses').mockResolvedValue(undefined)
      const wrapper = await advanceToStep2()
      // default value is '' → "No grade"
      await wrapper.find('[data-testid="finish-btn"]').trigger('click')
      await flushPromises()
      expect(updateSpy).toHaveBeenCalledWith([{ course_code: 'CSCI1300' }])
    })
  })
})
