import CodeMirror from '@uiw/react-codemirror';
import { python } from '@codemirror/lang-python';
import { vscodeDark } from "@uiw/codemirror-theme-vscode"; // Um tema escuro legal

/**
 * ATUALIZADO: Componente agora é editável e reporta mudanças
 * @param {object} props
 * @param {string[]} props.source - Array de linhas de código.
 * @param {function} props.onChange - Função para chamar quando o código mudar.
 * @param {function} props.onFocus - Função para chamar quando a célula for clicada.
 */
function CodeCell({ source, onChange, onFocus }) {
  // ATUALIZADO: Usamos .join('\n') para garantir a quebra de linha correta
  // entre os elementos do array.
  const code = source.join('\n');

  return (
    <div className="CodeCell" onClick={onFocus}>
      <CodeMirror
        value={code}
        height="auto"
        minHeight="40px"
        theme={vscodeDark}
        extensions={[python()]}

        // ATUALIZADO: Removemos o readOnly={true}

        // ATUALIZADO: Passa o novo valor (string) para o handler
        onChange={onChange}

        // ATUALIZADO: Informa o componente pai que esta célula está em foco
        onFocus={onFocus}

        basicSetup={{
          lineNumbers: true, // ATUALIZADO: Vamos mostrar números de linha
          foldGutter: true,
          autocompletion: true,
          searchKeymap: true,
          syntaxHighlighting: true,
          // Desativa o highlight da linha ativa, 
          // vamos controlar isso com CSS
          highlightActiveLine: false, 
          highlightActiveLineGutter: false,
        }}
      />
    </div>
  );
}

export default CodeCell;