import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// Model output is untrusted: retain the renderer's safe URLs, skip raw HTML,
// and show image descriptions without fetching model-selected remote assets.
const components = {
  img: ({alt}) => <span>{alt || 'Image omitted'}</span>,
  table: ({children}) => <div className="analysis-table"><table>{children}</table></div>,
}

export default function AnalysisMarkdown({children}) {
  return <div className="analysis-text"><Markdown remarkPlugins={[remarkGfm]} skipHtml components={components}>{children}</Markdown></div>
}
