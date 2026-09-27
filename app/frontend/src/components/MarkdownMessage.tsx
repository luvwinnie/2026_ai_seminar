/**
 * MarkdownMessage — チャット回答のMarkdownレンダリング。
 *
 * - GFM(表・リスト・太字等)対応。[KZ25-XXXX] / KZ25-XXXX は報告書詳細への内部リンク化
 * - アプリ内リンク(/reports/…)は React Router で遷移、外部リンクは新規タブ
 * - チャット気泡向けに余白をコンパクトに調整
 */
import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link as RouterLink } from 'react-router-dom'
import { Link, Box } from '@mui/material'
import { MONO_FONT } from '../theme'

// 裸の KZ25-XXXX / [KZ25-XXXX] をMarkdownリンクへ前処理(既存リンク内は二重変換しない)
function linkifyDefectIds(text: string): string {
  return text
    .replace(/\[(KZ25-\d{4})\](?!\()/g, '[$1](/reports/$1)')
    .replace(/(?<![[/\w])(KZ25-\d{4})(?!\]|\d)/g, '[$1](/reports/$1)')
}

function MarkdownMessageInner({ text }: { text: string }) {
  return (
    <Box
      sx={{
        '& p': { m: 0, mb: 1, '&:last-child': { mb: 0 } },
        '& ul, & ol': { m: 0, mb: 1, pl: 2.5, '&:last-child': { mb: 0 } },
        '& li': { mb: 0.25 },
        '& h1, & h2, & h3, & h4': { m: 0, mb: 0.75, mt: 1, fontSize: '1.02em', fontWeight: 700 },
        '& code': {
          fontFamily: MONO_FONT,
          fontSize: '0.85em',
          px: 0.5,
          py: 0.1,
          borderRadius: 0.5,
          bgcolor: 'action.hover',
        },
        '& pre': {
          p: 1,
          borderRadius: 1,
          bgcolor: 'action.hover',
          overflowX: 'auto',
          '& code': { p: 0, bgcolor: 'transparent' },
        },
        '& table': { borderCollapse: 'collapse', mb: 1, display: 'block', overflowX: 'auto' },
        '& th, & td': { border: '1px solid', borderColor: 'divider', px: 1, py: 0.5, fontSize: '0.9em' },
        '& blockquote': { m: 0, mb: 1, pl: 1.5, borderLeft: '3px solid', borderColor: 'divider', color: 'text.secondary' },
        '& hr': { border: 0, borderTop: '1px solid', borderColor: 'divider', my: 1 },
        lineHeight: 1.7,
        wordBreak: 'break-word',
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) =>
            href?.startsWith('/') ? (
              <Link component={RouterLink} to={href} sx={{ fontWeight: 700 }}>
                {children}
              </Link>
            ) : (
              <Link href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </Link>
            ),
        }}
      >
        {linkifyDefectIds(text)}
      </ReactMarkdown>
    </Box>
  )
}

const MarkdownMessage = memo(MarkdownMessageInner)
export default MarkdownMessage
