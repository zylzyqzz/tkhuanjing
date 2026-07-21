export const tokens={
  color:{brand:'#2563EB',brandHover:'#1D4ED8',nav:'#102A56',background:'#F5F7FB',surface:'#FFFFFF',text:'#172033',muted:'#6B7280',border:'#E3E8F1',success:'#169B6B',warning:'#D88716',danger:'#D94150',info:'#3978F6'},
  font:{page:'26px',section:'19px',metric:'32px',body:'14px',caption:'12px'},
  space:{xs:'4px',sm:'8px',md:'16px',lg:'24px',xl:'32px'},
  radius:{sm:'8px',md:'12px',lg:'16px',pill:'999px'},
  shadow:{card:'0 6px 20px rgba(27,53,88,.07)',float:'0 16px 40px rgba(27,53,88,.12)'},
  motion:{fast:'120ms',normal:'200ms',slow:'320ms'},
  breakpoint:{mobile:'800px',tablet:'1100px',desktop:'1440px'}
} as const

export const cssVariables=Object.entries({
  '--color-brand':tokens.color.brand,'--color-brand-hover':tokens.color.brandHover,'--color-nav':tokens.color.nav,
  '--color-bg':tokens.color.background,'--color-surface':tokens.color.surface,'--color-text':tokens.color.text,
  '--color-muted':tokens.color.muted,'--color-border':tokens.color.border,'--color-success':tokens.color.success,
  '--color-warning':tokens.color.warning,'--color-danger':tokens.color.danger,'--radius-card':tokens.radius.lg,
  '--shadow-card':tokens.shadow.card,'--shadow-float':tokens.shadow.float,'--motion-normal':tokens.motion.normal
}).map(([key,value])=>`${key}:${value}`).join(';')
