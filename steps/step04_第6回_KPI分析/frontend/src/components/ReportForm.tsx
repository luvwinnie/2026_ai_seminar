import { Box, Checkbox, FormControlLabel, MenuItem, TextField, Typography } from '@mui/material'
import type { ReactNode } from 'react'
import type { ReportInput } from '../types'
import {
  CATEGORIES_4M,
  CATEGORY_4M_LABELS,
  CUSTOMERS,
  FACTORS,
  MACHINES,
  PHENOMENA,
  PROCESSES,
  SEVERITIES,
  SEVERITY_LABELS,
  STATUSES,
  STATUS_LABELS,
} from '../constants/vocab'

interface Props {
  value: ReportInput
  onChange: (patch: ReportInput) => void
}

/** フォーム内のセクション見出し + レスポンシブグリッド */
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1.5, color: 'primary.main' }}>
        {title}
      </Typography>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
          gap: 2,
        }}
      >
        {children}
      </Box>
    </Box>
  )
}

/** 2列にまたがるフィールド用ラッパー */
function Full({ children }: { children: ReactNode }) {
  return <Box sx={{ gridColumn: { xs: '1', sm: '1 / -1' } }}>{children}</Box>
}

export default function ReportForm({ value, onChange }: Props) {
  // テキスト系フィールドの共通ハンドラ
  const text = (field: keyof ReportInput) => ({
    value: (value[field] as string | number | undefined) ?? '',
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => onChange({ [field]: e.target.value }),
    size: 'small' as const,
    fullWidth: true,
  })

  // 数値フィールド(空文字は undefined に)
  const num = (field: keyof ReportInput) => ({
    value: (value[field] as number | undefined) ?? '',
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      onChange({ [field]: e.target.value === '' ? undefined : Number(e.target.value) }),
    size: 'small' as const,
    fullWidth: true,
    type: 'number',
  })

  const bool = (field: keyof ReportInput) => ({
    checked: Boolean(value[field]),
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => onChange({ [field]: e.target.checked }),
  })

  return (
    <Box>
      <Section title="基本情報">
        <TextField
          label="発生日"
          type="date"
          slotProps={{ inputLabel: { shrink: true } }}
          {...text('occurrence_date')}
        />
        <TextField
          label="報告日"
          type="date"
          slotProps={{ inputLabel: { shrink: true } }}
          {...text('report_date')}
        />
        <TextField select label="客先" {...text('customer')}>
          {CUSTOMERS.map((c) => (
            <MenuItem key={c} value={c}>
              {c}
            </MenuItem>
          ))}
        </TextField>
        <TextField label="発見者名" {...text('discoverer')} />
        <TextField label="部品番号" {...text('part_number')} />
        <TextField label="部品名称" {...text('part_name')} />
      </Section>

      <Section title="不具合内容">
        <TextField select label="発生工程" {...text('process')}>
          {PROCESSES.map((p) => (
            <MenuItem key={p} value={p}>
              {p}
            </MenuItem>
          ))}
        </TextField>
        <TextField select label="使用機械" {...text('machine_name')}>
          {MACHINES.map((m) => (
            <MenuItem key={m} value={m}>
              {m}
            </MenuItem>
          ))}
        </TextField>
        <TextField label="作業者名" {...text('operator_name')} />
        <TextField select label="現象分類" {...text('phenomenon')}>
          {PHENOMENA.map((p) => (
            <MenuItem key={p} value={p}>
              {p}
            </MenuItem>
          ))}
        </TextField>
        <TextField label="加工数" {...num('production_count')} />
        <TextField label="不適合数" {...num('defect_count')} />
        <Full>
          <TextField label="不具合内容" multiline minRows={2} {...text('defect_description')} />
        </Full>
        <Full>
          <TextField label="良品状態(あるべき状態)" multiline minRows={2} {...text('good_condition')} />
        </Full>
      </Section>

      <Section title="原因・4M分析">
        <Full>
          <TextField label="原因" multiline minRows={2} {...text('cause')} />
        </Full>
        <TextField select label="要因" {...text('factor')}>
          <MenuItem value="">(未選択)</MenuItem>
          {FACTORS.map((f) => (
            <MenuItem key={f} value={f}>
              {f}
            </MenuItem>
          ))}
        </TextField>
        <TextField select label="4M分類" {...text('category_4m')}>
          <MenuItem value="">(未分類)</MenuItem>
          {CATEGORIES_4M.map((c) => (
            <MenuItem key={c} value={c}>
              {CATEGORY_4M_LABELS[c]}
            </MenuItem>
          ))}
        </TextField>
        <TextField select label="重要度" {...text('severity')}>
          {SEVERITIES.map((s) => (
            <MenuItem key={s} value={s}>
              {SEVERITY_LABELS[s]}
            </MenuItem>
          ))}
        </TextField>
        <TextField select label="ステータス" {...text('status')}>
          {STATUSES.map((s) => (
            <MenuItem key={s} value={s}>
              {STATUS_LABELS[s]}
            </MenuItem>
          ))}
        </TextField>
        <Full>
          <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
            <FormControlLabel control={<Checkbox {...bool('is_recurrence')} />} label="再発案件" />
            <FormControlLabel control={<Checkbox {...bool('has_procedure')} />} label="手順書あり" />
          </Box>
        </Full>
      </Section>

      <Section title="対策">
        <Full>
          <TextField label="対策" multiline minRows={2} {...text('countermeasure')} />
        </Full>
        <Full>
          <TextField label="備考" multiline minRows={2} {...text('notes')} />
        </Full>
      </Section>

      <Section title="費用(円)">
        <TextField label="材料費" {...num('material_cost')} />
        <TextField label="社内加工費" {...num('processing_cost')} />
        <TextField label="外注加工費" {...num('outsourcing_cost')} />
        <TextField label="その他費用" {...num('other_cost')} />
        <TextField label="合計損失(未入力ならサーバ側で合算)" {...num('total_cost')} />
      </Section>
    </Box>
  )
}
