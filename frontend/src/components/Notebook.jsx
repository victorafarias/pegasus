import CodeCell from './CodeCell';
import MarkdownCell from './MarkdownCell';
import CellOutput from './CellOutput';

/**
 * ATUALIZADO: Passa o handler de 'Run' e renderiza a saída
 * @param {object} props
 * @param {object} props.notebook - O objeto notebook.
 * @param {number} props.activeCellIndex - O índice da célula ativa.
 * @param {function} props.onCellChange - Handler para mudança de conteúdo.
 * @param {function} props.onCellFocus - Handler para clique/foco.
 * @param {function} props.onRunCell - Handler para executar a célula.
 */

function Notebook({ 
  notebook, 
  activeCellIndex, 
  onCellChange, 
  onCellFocus, 
  onRunCell,
  onDeleteCell,
  onMoveCell
}) {
  if (!notebook || !notebook.cells) {
    return <div className="NotebookPlaceholder">Abra um notebook para começar.</div>;
  }

  const cellCount = notebook.cells.length;
  
  return (
    <div className="Notebook">
      {notebook.cells.map((cell, index) => {
        const isActive = index === activeCellIndex;
        const handleFocus = () => onCellFocus(index);
        const handleChange = (newValue) => onCellChange(index, newValue);
        const handleRun = (e) => {
          e.stopPropagation(); 
          onRunCell(index);
        };
        // ATUALIZADO: Handler para excluir
        const handleDelete = (e) => {
          e.stopPropagation();
          onDeleteCell(index);
        };
        // ATUALIZADO: Handlers para Mover Célula
        const handleMoveUp = (e) => {
          e.stopPropagation();
          onMoveCell(index, 'up');
        };
        const handleMoveDown = (e) => {
          e.stopPropagation();
          onMoveCell(index, 'down');
        };

        const output = cell.outputs && cell.outputs[0];

        return (
          <div 
            key={index} 
            className={`CellWrapper ${isActive ? 'active' : ''}`}
          >
            {/* ATUALIZADO: Coluna 1 (Gutter Esquerda) */}
            <div className="CellGutter-left">
              {cell.cell_type === 'code' && (
                <button className="RunButton" onClick={handleRun}>
                  ▶
                </button>
              )}
            </div>

            {/* Coluna 2 (Conteúdo) */}
            <div className="CellContent">
              {cell.cell_type === 'code' ? (
                <CodeCell
                  source={cell.source}
                  onChange={handleChange}
                  onFocus={handleFocus}
                />
              ) : (
                <MarkdownCell
                  source={cell.source}
                  isActive={isActive}
                  onChange={handleChange}
                  onFocus={handleFocus}
                />
              )}
              <CellOutput output={output} />
            </div>

            {/* ATUALIZADO: Nova Coluna 3 (Gutter Direita) */}
            <div className="CellGutter-right">
              {/* O botão de excluir foi MOVIDO para cá */}
              <button className="Cell-delete-btn" onClick={handleDelete}>
                &times; {/* Este é um 'X' de fechar */}
              </button>
              <button 
                className="Cell-move-btn" 
                title="Mover para Cima"
                onClick={handleMoveUp}
                disabled={index === 0} // Desabilita se for a primeira
              >
                &#x25B2; {/* Seta para Cima */}
              </button>
              <button 
                className="Cell-move-btn" 
                title="Mover para Baixo"
                onClick={handleMoveDown}
                disabled={index === cellCount - 1} // Desabilita se for a última
              >
                &#x25BC; {/* Seta para Baixo */}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default Notebook;