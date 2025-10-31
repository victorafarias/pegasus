/**
 * Renderiza o bloco de saída (stdout ou stderr) de uma célula.
 * @param {object} props
 * @param {object} props.output - O objeto de saída (ex: {type: 'stdout', content: '...'})
 */
function CellOutput({ output }) {
  if (!output) return null;

  // Adiciona uma classe CSS com base no tipo de saída
  const className = `CellOutput ${output.type || 'stdout'}`;

  // Usa <pre> para preservar espaços em branco e quebras de linha
  return (
    <pre className={className}>
      {output.content}
    </pre>
  );
}

export default CellOutput;