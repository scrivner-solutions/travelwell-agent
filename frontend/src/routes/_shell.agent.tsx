import { createFileRoute } from '@tanstack/react-router'
import { AgentScreen } from '@/features/agent/AgentScreen'

export const Route = createFileRoute('/_shell/agent')({
  component: AgentScreen,
})
