export function mealPanel({api, run, outputs, importBlob, message}) {
  const el = id => document.getElementById(id);
  let snapshot, request, page = 0, generation = 0;
  function invalidate() {
    generation++;
    snapshot = request = null;
    el('mealResult').classList.add('hidden');
    el('outputs').classList.add('hidden');
    el('mealCsv').disabled = true;
  }
  for (const id of ['mealFromTotals','mealMonth','mealSchools','mealGroups','mealModel','mealReference']) el(id).onchange = invalidate;
  function renderRows() {
    if (!snapshot) return;
    const filter = el('mealFilter').value.toLocaleLowerCase('it');
    const data = snapshot[el('mealView').value];
    const rows = data.slice(1).filter(row => row.join(' ').toLocaleLowerCase('it').includes(filter));
    const pages = Math.max(1, Math.ceil(rows.length / 30));
    page = Math.max(0, Math.min(page,pages-1));
    function rowEl(values, tag) {
      const tr = document.createElement('tr');
      for (const value of values) {
        const cell = document.createElement(tag);
        cell.textContent = value;
        tr.append(cell);
      }
      return tr;
    }
    el('mealHead').replaceChildren(rowEl(data[0] || [],'th'));
    el('mealRows').replaceChildren(...rows.slice(page*30,(page+1)*30).map(r => rowEl(r,'td')));
    el('mealPage').textContent = (page+1)+' / '+pages;
    el('mealPrev').disabled = page===0;
    el('mealNext').disabled = page+1>=pages;
  }
  el('mealView').onchange = () => { page=0; renderRows(); };
  el('mealFilter').oninput = () => { page=0; renderRows(); };
  el('mealPrev').onclick = () => { page--; renderRows(); };
  el('mealNext').onclick = () => { page++; renderRows(); };
  el('mealPreview').onclick = () => run(async () => {
    invalidate();
    const current = generation;
    const period = el('mealMonth').value;
    const schools = Array.from(el('mealSchools').files);
    const groups = el('mealGroups').files[0];
    const model = el('mealModel').files[0], reference = el('mealReference').files[0];
    if (!period || !schools.length) throw Error('Scegli il mese e almeno un prospetto della scuola.');
    const load = async f => f ? (await importBlob(f,f.name)).id : '';
    const input = {cmd:'mensa', period, schools:[], fromTotals:el('mealFromTotals').checked};
    for (const file of schools) input.schools.push(await load(file));
    input.groupsFile = await load(groups);
    input.model = await load(model);
    input.reference = await load(reference);
    const result = await api(input);
    if (generation!==current) return;
    request = input;
    snapshot = result;
    const s = result.summary;
    el('mealSummary').textContent = s.students+' alunni · '+s.meals+' pasti alunni · '+s.teachers+' docenti esclusi ('+s.teacherMeals+' pasti) · '+s.duplicates+' righe riepilogative ripetute · '+s.matched+' abbinati · '+s.missingCF+' alunni senza codice fiscale.';
    el('mealDraft').classList.toggle('hidden',!result.draftReady);
    el('mealView').options[3].disabled = !result.grid.length;
    if (result.grid.length) el('mealSummary').textContent += ' '+result.symbols+' X nelle righe abbinate.';
    el('mealView').options[2].disabled = !result.courses.length;
    el('mealView').value = result.courses.length ? 'courses' : 'classes';
    el('mealFilter').value = '';
    if (result.courses.length) el('mealSummary').textContent += ' Il modello del gestionale comprende '+(result.courses.length-1)+' righe alunno.';
    const checks = [...result.issues,...result.notes];
    el('mealIssues').textContent = checks.length ? checks.join('\n') : 'Tutti i controlli completati.';
    el('mealIssues').style.whiteSpace = 'pre-line';
    el('mealResult').classList.remove('hidden');
    el('mealCsv').disabled = !result.ready;
    page=0; renderRows();
    message(result.ready?'Anteprima pronta. Verifica i giorni prima di creare il CSV.':'Anteprima pronta. Consulta le segnalazioni.');
  });
  for (const [id,action] of [['mealReview','review'],['mealDraft','draft'],['mealCsv','csv']]) {
    el(id).onclick = () => run(async () => {
      if (!snapshot) throw Error('Ripeti l’anteprima.');
      await outputs(await api({...request,action,token:snapshot.token}));
      if (action==='csv') el('mealCsv').disabled=true;
    });
  }
}
