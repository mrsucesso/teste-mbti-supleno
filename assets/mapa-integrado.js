/* Mapa Integrado Supleno: combinação local, transparente e determinística,
 * sem nova pontuação; não é diagnóstico. */
(function (global) {
  'use strict';

  var PRODUTOS = ['tipos', 'estilos', 'tracos'];
  var LABELS = { tipos: 'Supleno Tipos', estilos: 'Supleno Estilos', tracos: 'Supleno Traços' };

  function combinar(registros) {
    registros = registros || {};
    var dados = {};
    var faltam = [];
    PRODUTOS.forEach(function (produto) {
      var registro = registros[produto];
      if (!Object.prototype.hasOwnProperty.call(registros, produto) && global.SuplenoProgresso && global.SuplenoProgresso.ler) {
        registro = global.SuplenoProgresso.ler(produto);
      }
      if (!registro || !registro.resultado) faltam.push(produto);
      else dados[produto] = registro.resultado;
    });
    return {
      completo: faltam.length === 0,
      faltam: faltam,
      dados: dados,
      tipo: dados.tipos && dados.tipos.code,
      // Estilos gravava `{code: ...}` desde a captura v1; aceite também o
      // formato legado string para não quebrar registros já existentes.
      estilo: typeof dados.estilos === 'string' ? dados.estilos :
        (dados.estilos && typeof dados.estilos.code === 'string' ? dados.estilos.code : null),
      tracos: dados.tracos || null,
      regra: 'O mapa apenas reúne os três resultados locais; não soma, hierarquiza nem transforma um resultado em diagnóstico.'
    };
  }

  function textoCompartilhamento(mapa) {
    if (!mapa.completo) return 'Meu Mapa Integrado Supleno ainda está incompleto. Faltam: ' + mapa.faltam.map(function (p) { return LABELS[p]; }).join(', ') + '.';
    return 'Meu Mapa Integrado Supleno reúne Tipos ' + mapa.tipo + ', Estilos ' + mapa.estilo + ' e Traços. É uma leitura educativa, não um diagnóstico: ' + mapa.regra;
  }

  global.SuplenoMapa = { produtos: PRODUTOS.slice(), combinar: combinar, textoCompartilhamento: textoCompartilhamento };
})(typeof window !== 'undefined' ? window : globalThis);
