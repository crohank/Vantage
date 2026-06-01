import { ToggleGroup, ToggleGroupItem } from './ui/toggle-group'
import { Label } from './ui/label'

type Horizon = 'short' | 'medium' | 'long'

interface HorizonSelectProps {
  value: Horizon
  onChange: (value: Horizon) => void
}

const OPTIONS: { value: Horizon; label: string; sublabel: string }[] = [
  { value: 'short', label: 'Short', sublabel: '< 3mo' },
  { value: 'medium', label: 'Medium', sublabel: '3-12mo' },
  { value: 'long', label: 'Long', sublabel: '> 1yr' }
]

function HorizonSelect({ value, onChange }: HorizonSelectProps) {
  return (
    <div className="space-y-1.5">
      <Label>Horizon</Label>
      <ToggleGroup
        type="single"
        value={value}
        onValueChange={(v) => v && onChange(v as Horizon)}
        className="w-full"
      >
        {OPTIONS.map((opt) => (
          <ToggleGroupItem key={opt.value} value={opt.value} className="flex-1 flex-col gap-0 py-1 h-auto">
            <span className="text-[12px] font-semibold">{opt.label}</span>
            <span className="font-mono text-[10px] text-muted-foreground">{opt.sublabel}</span>
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  )
}

export default HorizonSelect
