import { ToggleGroup, ToggleGroupItem } from './ui/toggle-group'
import { Label } from './ui/label'

type RiskProfile = 'conservative' | 'moderate' | 'aggressive'

interface RiskProfileSelectProps {
  value: RiskProfile
  onChange: (value: RiskProfile) => void
}

const OPTIONS: { value: RiskProfile; label: string; sublabel: string }[] = [
  { value: 'conservative', label: 'Conservative', sublabel: 'Low β' },
  { value: 'moderate', label: 'Moderate', sublabel: 'Balanced' },
  { value: 'aggressive', label: 'Aggressive', sublabel: 'High β' }
]

function RiskProfileSelect({ value, onChange }: RiskProfileSelectProps) {
  return (
    <div className="space-y-1.5">
      <Label>Risk Profile</Label>
      <ToggleGroup
        type="single"
        value={value}
        onValueChange={(v) => v && onChange(v as RiskProfile)}
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

export default RiskProfileSelect
