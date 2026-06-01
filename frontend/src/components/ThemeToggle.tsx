import { Moon, Sun } from 'lucide-react'
import { useTheme } from '../context/ThemeContext'
import { cn } from '../lib/utils'

interface ThemeToggleProps {
  className?: string
}

function ThemeToggle({ className }: ThemeToggleProps) {
  const { theme, toggle } = useTheme()
  const isDark = theme === 'dark'
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${isDark ? 'light' : 'dark'} theme`}
      title={`Switch to ${isDark ? 'light' : 'dark'} theme`}
      className={cn(
        'inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-surface text-muted-foreground transition-colors hover:bg-surface-elevated hover:text-foreground',
        className
      )}
    >
      {isDark ? <Sun size={15} /> : <Moon size={15} />}
    </button>
  )
}

export default ThemeToggle
