import { NavLink } from 'react-router-dom'
import { FileDiff } from 'lucide-react'
import ThemeToggle from './ThemeToggle'
import { cn } from '../lib/utils'

function TopNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="mx-auto flex h-12 max-w-screen-2xl items-center gap-6 px-4">
        <NavLink to="/findings" className="flex items-center gap-2">
          <span className="grid h-6 w-6 place-items-center rounded-sm bg-primary text-primary-foreground">
            <span className="font-mono text-[11px] font-bold leading-none">V</span>
          </span>
          <span className="font-mono text-[13px] font-semibold tracking-[0.15em] text-foreground">
            VANTAGE
          </span>
          <span className="hidden font-mono text-[10px] tracking-[0.2em] text-muted-foreground sm:inline">
            / DISCLOSURE INTELLIGENCE
          </span>
        </NavLink>

        <nav className="flex items-center gap-1">
          <NavItem to="/findings" icon={<FileDiff size={14} />} label="Findings" />
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}

interface NavItemProps {
  to: string
  icon: React.ReactNode
  label: string
}

function NavItem({ to, icon, label }: NavItemProps) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          'inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium transition-colors',
          isActive
            ? 'bg-surface-elevated text-foreground'
            : 'text-muted-foreground hover:bg-surface hover:text-foreground'
        )
      }
    >
      {icon}
      {label}
    </NavLink>
  )
}

export default TopNav
