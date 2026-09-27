import {test,expect,type Page} from '@playwright/test';
import {lessons} from '../src/learning/lessons';

const coach=(page:Page)=>page.locator('.learning-coach');
async function start(page:Page,deep=false){
  await page.goto('/');
  if(deep)await page.getByRole('radio',{name:/In-depth/}).check();
  await page.getByRole('button',{name:deep?'Start In-depth tutorial':'Start Basic tutorial',exact:true}).click();
  await expect(coach(page).getByRole('button',{name:'Next',exact:true})).toBeEnabled();
}
async function jump(page:Page,id:string){
  const i=lessons.findIndex(l=>l.id===id);
  await coach(page).locator('.learn-contents summary').click();
  await coach(page).getByRole('button',{name:`${i+1}. ${lessons[i].title}`,exact:true}).click();
  await expect(coach(page).locator('.learn-contents')).not.toHaveAttribute('open','');
  await expect(coach(page)).toHaveAttribute('data-target',id);
}
async function anchored(page:Page){
  await expect(coach(page)).toHaveAttribute('data-anchored','true');
  // Wait for the destination scroll to settle before checking physical geometry.
  await page.waitForTimeout(1100);
  const shape=await page.evaluate(()=>{
    const card=document.querySelector('.learning-coach')!.getBoundingClientRect();
    const focus=document.querySelector('.tour-spotlight')?.getBoundingClientRect();
    const next=document.querySelector('.learn-navigation .primary-button')!.getBoundingClientRect();
    const real=document.querySelector('[data-tour-anchor]')?.getBoundingClientRect();
    const arrow=document.querySelector('.learn-pointer')?.getBoundingClientRect();
    return {
      card:{x:card.x,y:card.y,w:card.width,h:card.height},
      fits:card.left>=0&&card.top>=0&&card.right<=document.documentElement.clientWidth+1&&card.bottom<=innerHeight+1,
      nextVisible:next.top>=card.top&&next.bottom<=card.bottom+1,
      targetVisible:!!focus&&focus.width>=20&&focus.height>=18,
      overlap:focus?Math.max(0,Math.min(card.right,focus.right)-Math.max(card.left,focus.left))*Math.max(0,Math.min(card.bottom,focus.bottom)-Math.max(card.top,focus.top)):Infinity,
      pointerGap:focus&&arrow?Math.min(Math.abs(arrow.right-focus.left),Math.abs(arrow.left-focus.right),Math.abs(arrow.bottom-focus.top),Math.abs(arrow.top-focus.bottom)):Infinity,
      targetAligned:!!focus&&!!real&&focus.left>=real.left-1&&focus.right<=real.right+1&&focus.top>=real.top-1&&focus.bottom<=real.bottom+1,
      overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth+1,
    };
  });
  expect(shape.fits).toBe(true);expect(shape.nextVisible).toBe(true);expect(shape.targetVisible).toBe(true);
  expect(shape.overlap).toBeLessThan(2);expect(shape.pointerGap).toBeLessThan(24);expect(shape.targetAligned).toBe(true);expect(shape.overflow).toBe(false);
  return shape.card;
}

test('guide moves to precise controls and leaves them usable',async({page})=>{
  test.setTimeout(90000);await start(page);await jump(page,'volume');const initial=await anchored(page);
  await coach(page).getByRole('button',{name:'Next',exact:true}).click();
  await expect(page.getByLabel('Cutaway',{exact:true})).toHaveAttribute('data-tour-anchor','');
  const cutaway=await anchored(page);expect(Math.abs(cutaway.x-initial.x)+Math.abs(cutaway.y-initial.y)).toBeGreaterThan(30);
  await page.getByLabel('Cutaway',{exact:true}).click();await expect(page.getByLabel('Cutaway',{exact:true})).toHaveAttribute('aria-pressed','false');
  await coach(page).getByRole('button',{name:'Next',exact:true}).click();await expect(page.getByLabel('Explorer depth')).toHaveAttribute('data-tour-anchor','');await anchored(page);
  await page.getByLabel('Explorer depth').selectOption({label:'200 m'});await expect(page.getByLabel('Explorer depth').locator('option:checked')).toHaveText('200 m');
  await jump(page,'salinity');await anchored(page);await expect(page.locator('.variable-selector')).toHaveAttribute('data-tour-anchor','');
  expect(await page.locator('.main-layout').evaluate(e=>getComputedStyle(e).marginRight)).toBe('0px');
});

test('guide fits short portrait and landscape, follows resize, and anchors charts',async({page})=>{
  test.setTimeout(90000);await start(page);
  for(const size of [{width:320,height:568},{width:844,height:390},{width:768,height:900}]){
    await page.setViewportSize(size);await jump(page,'volume');await anchored(page);
    await jump(page,'profile');await expect(coach(page).getByRole('button',{name:'Next',exact:true})).toBeEnabled();await anchored(page);
  }
});

test('manual scrolling is not fought and the guide brings a lost target back',async({page})=>{
  await start(page);await jump(page,'salinity');await anchored(page);
  await page.evaluate(()=>window.scrollTo({top:document.documentElement.scrollHeight,behavior:'instant'}));
  await expect(coach(page)).toHaveAttribute('data-anchored','false');
  await expect(coach(page).getByRole('button',{name:'Bring this view back'})).toBeVisible();
  const position=await page.evaluate(()=>scrollY);await page.waitForTimeout(400);expect(await page.evaluate(()=>scrollY)).toBeCloseTo(position,0);
  await coach(page).getByRole('button',{name:'Bring this view back'}).click();await anchored(page);
  await coach(page).getByRole('button',{name:'Skip',exact:true}).click();await expect(page.locator('.tour-spotlight,[data-tour-anchor],.tour-scroll-space')).toHaveCount(0);
});

test('save guidance appears at the name field inside the real modal without saving',async({page})=>{
  const captures:string[]=[];page.on('request',request=>{if(request.url().includes('/api/investigations/capture'))captures.push(request.url());});
  await start(page);await jump(page,'save');
  const dialog=page.getByRole('dialog',{name:'Saved investigations'});
  await expect(dialog.getByRole('note')).toContainText('Keep this investigation');
  await expect(dialog.getByLabel('Investigation name')).toBeVisible();await expect(coach(page)).toBeHidden();
  await dialog.getByRole('button',{name:'Close form and continue tutorial'}).click();await expect(dialog).toHaveCount(0);
  await anchored(page);
  await coach(page).getByRole('button',{name:'Next',exact:true}).click();await expect(coach(page)).toContainText('The essentials are covered.');
  expect(captures).toEqual([]);
});

test('in-depth pages and keyboard focus remain usable with enlarged text and reduced motion',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});await page.setViewportSize({width:768,height:900});await start(page,true);await jump(page,'volume');
  await page.addStyleTag({content:'html{font-size:200% !important}'});
  await coach(page).getByRole('button',{name:'Method',exact:true}).click();
  const next=coach(page).getByRole('button',{name:'Next',exact:true});await expect(next).toBeInViewport();expect(await next.evaluate(e=>{const r=e.getBoundingClientRect(),c=e.closest('.learning-coach')!.getBoundingClientRect();return r.top>=c.top&&r.bottom<=c.bottom+1&&r.bottom<=innerHeight;})).toBe(true);
  await next.focus();await page.keyboard.press('Enter');await expect(coach(page).getByRole('heading',{name:'Open a window into the water'})).toBeFocused();
  await expect(coach(page).getByRole('button',{name:'Skip',exact:true})).toBeInViewport();
});
