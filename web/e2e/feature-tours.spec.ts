import {test,expect,type Page} from '@playwright/test';
import {featureTours} from '../src/learning/featureTours';
import {lessons} from '../src/learning/lessons';

const picker=(page:Page)=>page.getByRole('dialog',{name:'What will you try next?',exact:true});
const coach=(page:Page)=>page.locator('.learning-coach');
async function open(page:Page){await page.goto('/');await page.getByRole('button',{name:/Explore extra feature tutorials/}).click();await expect(picker(page)).toBeVisible();}
async function select(page:Page,index:number){for(let i=0;i<Math.floor(index/2);i++)await picker(page).getByRole('button',{name:'More features',exact:true}).click();await picker(page).getByRole('button',{name:`Start ${featureTours[index].title} tutorial`,exact:true}).click();}

test('teasers and all feature pages fit small screens and preserve the chosen style',async({page})=>{
  for(const size of [{width:320,height:568},{width:390,height:844},{width:844,height:390}]){
    await page.setViewportSize(size);await open(page);
    for(let p=0;p<Math.ceil(featureTours.length/2);p++){
      await expect(picker(page).getByRole('status')).toContainText(`${p+1} / ${Math.ceil(featureTours.length/2)}`);
      expect(await picker(page).evaluate(e=>{const r=e.getBoundingClientRect();return e.scrollHeight<=e.clientHeight+1&&r.top>=0&&r.bottom<=innerHeight+1&&e.scrollWidth<=e.clientWidth+1;})).toBe(true);
      for(const card of await picker(page).locator('.feature-tour-card').all())expect(await card.evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;})).toBe(true);
      if(p<Math.ceil(featureTours.length/2)-1)await picker(page).getByRole('button',{name:'More features',exact:true}).click();
    }
    await picker(page).getByLabel('Extra feature tutorial style').selectOption('deep');await page.keyboard.press('Escape');
    await expect(page.getByRole('radio',{name:/In-depth/})).toBeChecked();await expect(page.getByRole('button',{name:'Start In-depth tutorial',exact:true})).toBeFocused();
  }
});

for(const [index,tour] of featureTours.entries())test(`${tour.title} teaser starts a self-contained guided demonstration`,async({page})=>{
  test.setTimeout(120000);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await open(page);await select(page,index);
  for(const [i,id] of tour.lessonIds.entries()){
    if(lessons.find(l=>l.id===id)!.action.action==='save')await page.getByRole('button',{name:'Close form and continue tutorial'}).click();
    await expect(coach(page).getByRole('heading',{level:2})).toHaveText(lessons.find(item=>item.id===id)!.title);
    await expect(coach(page).getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});
    await expect(coach(page).getByLabel('Tutorial result')).toBeVisible();await expect(coach(page)).toHaveAttribute('data-anchored','true');
    await expect(coach(page).locator('.learn-step-label')).toContainText(`${i+1} / ${tour.lessonIds.length}`);
    if(i===0)await expect(coach(page).getByRole('button',{name:'Previous tutorial step'})).toBeDisabled();
    if(id==='drift'){await expect(page.getByLabel('Applied drift run A')).toContainText('8 simulated particles');await expect(coach(page).getByLabel('Tutorial result')).toContainText('6 hours');}
    if(id==='climate')await expect(coach(page).getByLabel('Tutorial result')).toContainText('2015');
    if(id==='la-nina')await expect(coach(page).getByLabel('Tutorial result')).toContainText('La Niña');
    if(id==='blackout')await expect(coach(page).getByLabel('Tutorial result')).toContainText('103');
    await coach(page).getByRole('button',{name:'Next',exact:true}).click();
  }
  await expect(coach(page).getByRole('heading',{name:`End of the ${tour.title} tour`,exact:true})).toBeVisible();
  await coach(page).getByRole('button',{name:'Try another feature'}).click();await expect(picker(page)).toBeVisible();
  await picker(page).getByRole('button',{name:'Back to guide',exact:true}).click();await coach(page).getByRole('button',{name:'Explore on my own'}).click();
  await expect(coach(page)).toHaveCount(0);await expect(page.locator('.tour-spotlight')).toHaveCount(0);expect(errors).toEqual([]);
});

test('core completion offers specific extra tours, with In-depth concepts and a return path',async({page})=>{
  await page.goto('/');await page.getByRole('button',{name:'Start Basic tutorial',exact:true}).click();
  const save=lessons.findIndex(l=>l.id==='save');await coach(page).locator('.learn-contents summary').click();await coach(page).getByRole('button',{name:`${save+1}. ${lessons[save].title}`,exact:true}).click();
  await page.getByRole('button',{name:'Close form and continue tutorial'}).click();await coach(page).getByRole('button',{name:'Next',exact:true}).click();
  await coach(page).getByRole('button',{name:'Choose an extra feature'}).click();await picker(page).getByLabel('Extra feature tutorial style').selectOption('deep');await select(page,featureTours.findIndex(t=>t.id==='climate'));
  await expect(coach(page).getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});await coach(page).getByRole('button',{name:'Method',exact:true}).click();await expect(coach(page)).toContainText('1991-2020');
  await coach(page).getByRole('button',{name:'Extra features',exact:true}).click();await page.keyboard.press('Escape');
  await expect(coach(page).getByRole('heading',{name:'Compare an El Niño season'})).toBeVisible();await expect(coach(page).getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});
  await coach(page).getByRole('button',{name:'Skip',exact:true}).click();await page.getByRole('button',{name:'Quick guide'}).click();await page.getByRole('button',{name:'Start In-depth tutorial',exact:true}).click();await expect(coach(page).getByRole('heading',{name:lessons[0].title})).toBeVisible();
});

test('browsing teasers does not start a lab calculation and offers the complete extra tour',async({page})=>{
  const requests:string[]=[];page.on('request',r=>{if(r.url().includes('/api/'))requests.push(r.url());});
  await open(page);const before=requests.length;
  for(let i=0;i<3;i++)await picker(page).getByRole('button',{name:'More features',exact:true}).click();
  expect(requests.slice(before).filter(url=>/\/(drift|climate|heat|expedition|evolution|blackout|features|regional)(\/|\?)/.test(url))).toEqual([]);
  await picker(page).getByRole('button',{name:'Tour all extra features'}).click();await expect(coach(page).getByRole('heading',{name:'Ask the ocean a question'})).toBeVisible();await expect(coach(page).getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});
});

for(const cancel of [false,true])test(`a direct tour waits for a delayed catalogue${cancel?' and respects Skip':''}`,async({page})=>{
  let release!:()=>void;const gate=new Promise<void>(resolve=>release=resolve);
  await page.route('**/api/catalog',async route=>{await gate;try{await route.continue();}catch{}});
  await open(page);await select(page,featureTours.findIndex(t=>t.id==='drift'));await expect(coach(page).getByRole('heading',{name:'Drop a handful of virtual particles'})).toBeVisible();await expect(coach(page).getByLabel('Tutorial result')).toHaveCount(0);
  if(cancel)await coach(page).getByRole('button',{name:'Skip',exact:true}).click();release();
  if(cancel){await expect(page.getByLabel('Globe model case')).toBeVisible();await expect(page.locator('.current-activity')).toHaveText('Data globe');await expect(coach(page)).toHaveCount(0);}
  else{await expect(coach(page).getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});await expect(page.getByLabel('Applied drift run A')).toContainText('8 simulated particles');}
});
