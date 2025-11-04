import React, { useRef, useLayoutEffect } from 'react';

/**
 * Renderiza o bloco de saída (stdout ou stderr) de uma célula.
 * @param {object} props
 * @param {object} props.output - O objeto de saída (ex: {type: 'stdout', content: '...'})
 */
function CellOutput({ output }) {
  // A verificação de segurança (guard clause)
  // DEVE ser a primeira linha.
  // Se 'output' não existir, o componente para aqui.
  if (!output) return null;

  // O resto do código só roda se 'output' existir
  const outputRef = useRef(null);

  useLayoutEffect(() => {
    if (outputRef.current) {
      const element = outputRef.current;
      // Força a barra de rolagem para o final
      element.scrollTop = element.scrollHeight;
    }
  }, [output.content]); // Agora 'output.content' é seguro

  const className = `CellOutput ${output.type || 'stdout'}`;

  return (
    <pre className={className} ref={outputRef}>
      {output.content}
    </pre>
  );
}

export default CellOutput;