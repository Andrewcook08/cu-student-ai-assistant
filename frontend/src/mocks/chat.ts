import type { ChatMessage } from '@/types/index'

export const mockMessages: ChatMessage[] = [
  {
    role: 'user',
    content: 'What CS electives can I take next semester?',
  },
  {
    role: 'assistant',
    reply: 'Based on your completed courses, here are some **Computer Science electives** you might enjoy:\n\n- **CSCI 4229** — Computer Graphics (3 credits)\n- **CSCI 4831** — Quantum Computing (3 credits)\n- **CSCI 5502** — Data Mining (3 credits)\n- **CSCI 5622** — Machine Learning (3 credits)\n\nWould you like details on any of these?',
    structured_data: [
      {
        code: 'CSCI 4229',
        title: 'Computer Graphics',
        credits: '3',
        status: 'Open',
        instruction_mode: 'In Person',
        description: 'Introduction to computer graphics: OpenGL, transformations, lighting, textures.',
      },
      {
        code: 'CSCI 5622',
        title: 'Machine Learning',
        credits: '3',
        status: 'Open',
        instruction_mode: 'In Person',
        description: 'Supervised and unsupervised learning, neural networks, model evaluation.',
      },
    ],
    suggested_actions: [
      { type: 'search', label: 'Show all CSCI electives', payload: { dept: 'CSCI', level: 'undergrad-upper' } },
      { type: 'prereq', label: 'Check prerequisites for Machine Learning', payload: { course: 'CSCI 5622' } },
    ],
  },
]
