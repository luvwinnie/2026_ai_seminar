import { Box, Link } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import ReactMarkdown from 'react-markdown'
import { Link as RouterLink } from 'react-router-dom'
import remarkGfm from 'remark-gfm'

// 本文の報告書番号（[KZ25-XXXX] と KZ25-XXXX）を詳細へのリンクにする（05_UI設計書.md S3）。
// すでにリンクになっているもの（[…](/reports/KZ25-XXXX)）や、ほかの語の一部は変えない
const REPORT_ID = /\[(KZ25-\d{4})\](?!\()|(?<![\w/[-])(KZ25-\d{4})(?![\w\]])/g

export function linkReportIds(content: string): string {
  return content.replace(REPORT_ID, (_match, bracketed?: string, bare?: string) => {
    const id = bracketed ?? bare
    return `[${id}](/reports/${id})`
  })
}

export default function MarkdownMessage({ content }: { content: string }) {
  const theme = useTheme()
  return (
    <Box
      data-testid="chat-answer"
      sx={{
        '& p': { my: 0.75 },
        '& ul, & ol': { my: 0.75, pl: 3 },
        '& table': { borderCollapse: 'collapse', my: 1 },
        '& th, & td': { border: `1px solid ${theme.palette.divider}`, px: 1, py: 0.5 },
        '& code': { bgcolor: theme.palette.app.elevated, px: 0.5, borderRadius: 0.5 },
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // アプリの中のパスは React Router で移る（ページを読み直さない）
          a: ({ href, children }) =>
            href?.startsWith('/') ? (
              <Link component={RouterLink} to={href}>
                {children}
              </Link>
            ) : (
              <Link href={href} target="_blank" rel="noreferrer">
                {children}
              </Link>
            ),
        }}
      >
        {linkReportIds(content)}
      </ReactMarkdown>
    </Box>
  )
}
