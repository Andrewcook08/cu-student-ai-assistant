// Course Search types
export interface Course {
  code: string
  title: string
  credits: string // text field; can be "3", "1-3", or "Varies by section"
  dept: string
  description?: string
  prerequisites_raw?: string
  instruction_mode?: string
  status?: string
  topic_titles?: string
  attributes?: string[]
  sections?: Section[]
}

export interface Section {
  crn: string
  type?: string // LEC, REC, LAB, SEM, etc.
  section_number?: string
  meets?: string
  instructor?: string
  status: string
}

export interface Program {
  id: number
  name: string
  type: string
  total_credits?: number
}

export interface Requirement {
  id: number
  program_id: number
  sort_order: number
  requirement_type: string
  course_code?: string
  description?: string
}

export interface CompletedCourse {
  course_code: string
  grade?: string
}

export interface StudentDecision {
  course_code: string
  decision_type: string
  notes?: string
}

export interface StudentProfile {
  id: number
  email: string
  program?: Program
  completed_courses: CompletedCourse[]
  decisions: StudentDecision[]
}

export interface FilterValues {
  dept: string
  level: string
  credits: string
}

// Chat types
export interface CourseCard {
  code: string
  title: string
  credits: string // text field; can be "3", "1-3", or "Varies by section"
  description?: string
  topic_titles?: string
  instruction_mode?: string
  status?: string
  attributes?: string[]
}

export interface Action {
  type: string
  label: string
  payload?: Record<string, unknown>
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content?: string        // set for user-typed messages
  reply?: string          // set for AI WebSocket responses (WsServerMessage.reply)
  structured_data?: CourseCard[]
  suggested_actions?: Action[]
}

// WebSocket protocol types
export interface WsClientMessage {
  type: 'chat_message'
  message: string
  session_id?: string
  context?: {
    selected_program?: string
    completed_courses?: string[]
    action_response?: { type: string; value: string }
  }
}

export interface WsServerMessage {
  type: 'chat_response' | 'typing' | 'error' | 'progress' | 'token'
  reply?: string
  token?: string
  structured_data?: CourseCard[]
  suggested_actions?: Action[]
  session_id?: string
  error?: string
  message?: string
}

// API response types
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  offset: number
  limit: number
}

// Auth types
export interface AuthRegisterResponse {
  token: string
  user_id: number
}

export interface RegisterFormData {
  email: string
  password: string
  name: string
  program_id?: number
}

export interface CompletedCoursePayload {
  course_code: string
  grade?: string
}

export interface ProgramRequirementsResponse {
  program: Program
  requirements: Requirement[]
}
