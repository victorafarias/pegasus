import ReactMarkdown from 'react-markdown';
import CodeMirror from '@uiw/react-codemirror';
import { markdown, markdownLanguage } from '@codemirror/lang-markdown';
import { vscodeDark } from "@uiw/codemirror-theme-vscode";

/**
 * ATUALIZADO: Componente com dois modos (visualização e edição)
 * @param {object} props
 * @param {string[]} props.source - Array de linhas de Markdown.
 * @param {boolean} props.isActive - Se esta é a célula ativa.
 * @param {function} props.onChange - Função para chamar quando o texto mudar.
 * @param {function} props.onFocus - Função para chamar quando a célula for clicada.
 */

function MarkdownCell({ source, isActive, onChange, onFocus }) {
  // ATUALIZADO: .join('\n') é crucial para o Markdown renderizar corretamente
  const markdownText = source.join('\n');

  if (!isActive) {
    // --- Modo de Visualização ---
    // Renderiza o Markdown.
    // O onFocus vai "ativar" esta célula ao ser clicada.
    return (
      <div className="MarkdownCell view-mode" onClick={onFocus}>
        <ReactMarkdown>
          {markdownText}
        </ReactMarkdown>
      </div>
    );
  }

  // --- Modo de Edição ---
  // Renderiza um editor CodeMirror com a sintaxe de Markdown
  return (
    <div className="MarkdownCell edit-mode" onFocus={onFocus}>
      <CodeMirror
        value={markdownText}
        height="auto"
        minHeight="40px"
        theme={vscodeDark}
        extensions={[
          markdown({ base: markdownLanguage, codeLanguages: [] })
        ]}
        onChange={onChange}
        onFocus={onFocus} // Mantém o foco
        basicSetup={{
          lineNumbers: true,
          foldGutter: false,
          autocompletion: true,
          searchKeymap: true,
          syntaxHighlighting: true,
          highlightActiveLine: false,
          highlightActiveLineGutter: false,
        }}
      />
    </div>
  );
}

export default MarkdownCell;