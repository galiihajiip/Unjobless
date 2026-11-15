import type { LucideIcon } from 'lucide-react'
import {
  Bot,
  BriefcaseBusiness,
  ChartNoAxesCombined,
  Columns2,
  Compass,
  DatabaseZap,
  Download,
  LayoutDashboard,
  Radar,
  Settings,
  UserRound,
} from 'lucide-react'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  group: 'Workspace' | 'You' | 'Data' | 'System'
  description: string
}

export const NAV: NavItem[] = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, group: 'Workspace', description: 'Your career dashboard and source health.' },
  { to: '/discover', label: 'Discover', icon: Compass, group: 'Workspace', description: 'Verified vacancies matched to you.' },
  { to: '/signals', label: 'Opportunity Signals', icon: Radar, group: 'Workspace', description: 'Unverified leads and informal hiring signals.' },
  { to: '/compare', label: 'Compare', icon: Columns2, group: 'Workspace', description: 'Compare two vacancies side by side.' },
  { to: '/applications', label: 'Applications', icon: BriefcaseBusiness, group: 'Workspace', description: 'Track what you are preparing and have applied to.' },
  { to: '/profile', label: 'My Career Profile', icon: UserRound, group: 'You', description: 'Master profile, CV versions and preferences.' },
  { to: '/import', label: 'Import Center', icon: Download, group: 'Data', description: 'Import URLs or pasted content.' },
  { to: '/sources', label: 'Sources', icon: DatabaseZap, group: 'Data', description: 'Source registry, schedules and health.' },
  { to: '/intelligence', label: 'Career Intelligence', icon: ChartNoAxesCombined, group: 'Data', description: 'Employer sentiment, topics and trends.' },
  { to: '/ai', label: 'AI Studio', icon: Bot, group: 'System', description: 'AI providers, models and usage.' },
  { to: '/settings', label: 'Settings', icon: Settings, group: 'System', description: 'Preferences, security, backups and install help.' },
]

export const MOBILE_PRIMARY = ['/', '/discover', '/import', '/profile']
export const GROUPS: NavItem['group'][] = ['Workspace', 'You', 'Data', 'System']
