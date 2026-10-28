import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'
import assert from 'node:assert/strict'

const script = readFileSync(new URL('../native/app/src/main/assets/resolver.js', import.meta.url), 'utf8').replace('__JOB_ID__', '"job-test"').replace('__EXPECTED_ID__', '"123"')
const note = { aweme_id: '123', desc: '实际文案', images: [{ uri: 'first', url_list: ['https://cdn.example/1.webp'] }, null, { image_id: 'third', url_list: [] }] }
function setup(state = {}, source = script) {
  const messages = []
  let response
  const context = { URL, TextEncoder, TextDecoder, location: { href: 'https://www.douyin.com/note/123', pathname: '/note/123' }, document: { getElementById: () => null }, ...state }
  context.window = context
  context.ShiyingResult = { postMessage: text => messages.push(JSON.parse(text)) }
  context.fetch = () => Promise.resolve(response)
  vm.createContext(context)
  vm.runInContext(source, context)
  return { context, messages, async respond(url, data) { response = { status: 200, url, clone: () => ({ text: async () => JSON.stringify(data) }) }; await context.fetch(url); await new Promise(resolve => setImmediate(resolve)) } }
}

test('initial state matches target work and preserves image order and missing slots', () => {
  const { messages, context } = setup({ __INITIAL_STATE__: { list: [{ ...note, aweme_id: '456' }, note] } })
  assert.equal(messages[0].jobId, 'job-test')
  assert.equal(messages[0].detail.images.length, 3)
  assert.equal(messages[0].detail.images[1].uri, '')
  assert.equal(messages[0].detail.images[2].uri, 'third')
  assert.equal(context.__shiyingRead().desc, '实际文案')
})
test('observes post response and ignores unrelated domains and work IDs', async () => {
  const { messages, respond } = setup()
  await respond('https://evil.example/aweme/v1/web/aweme/detail/', { aweme_detail: note })
  await respond('https://www.douyin.com/aweme/v1/web/aweme/detail/', { aweme_detail: { ...note, aweme_id: '456' } })
  assert.equal(messages.length, 0)
  await respond('https://www.douyin.com/aweme/v1/web/aweme/post/?sec_user_id=x', { aweme_list: [note] })
  assert.equal(messages.length, 1)
  assert.equal(messages[0].detail.aweme_id, '123')
})
test('reads percent-encoded RENDER_DATA and tolerates repeated installation', () => {
  const { context, messages } = setup({ document: { getElementById: id => id === 'RENDER_DATA' ? { textContent: encodeURIComponent(JSON.stringify({ aweme: note })) } : null } })
  assert.equal(messages[0].detail.images[0].uri, 'first')
  assert.equal(vm.runInContext(script, context).aweme_id, '123')
})

test('short-link script receives its target from native after a modal redirect', () => {
  const lateScript = script.replace('const initialId = "123";', 'const initialId = "";')
  const { context, messages } = setup({ location: { href: 'https://www.douyin.com/?modal_id=123', pathname: '/' } },lateScript)
  context.__shiyingTargetId = '123'
  context.__INITIAL_STATE__ = { list: [note] }
  assert.equal(vm.runInContext(lateScript,context)?.aweme_id,'123')
  assert.equal(messages.at(-1).detail.aweme_id,'123')
})

test('reads target photo work from streamed page data, including split records', () => {
  const detail = { awemeId:'123',awemeType:68,authorInfo:{nickname:'作者'},desc:'四张图文',images:[
    {uri:'one',urlList:['https://cdn.example/1.webp']},
    {uri:'two',urlList:['https://cdn.example/2.webp']},
    {uri:'three',urlList:[]},
    {uri:'four',urlList:['https://cdn.example/4.webp']},
  ],video:{playAddr:[{src:'https://cdn.example/cover.mp4'}]} }
  const record = '7:'+JSON.stringify(['$','$L1',null,{aweme:{detail}}])+'\n'
  const {messages} = setup({__pace_f:[[1,'0:["$","$L1",null,{}]\n'],[1,record.slice(0,37)],[1,record.slice(37)]]})
  assert.equal(messages.length,1)
  assert.equal(messages[0].detail.author.nickname,'作者')
  assert.equal(messages[0].detail.aweme_type,68)
  assert.equal(messages[0].detail.images.length,4)
  assert.equal(messages[0].detail.images[2].uri,'three')
  assert.deepEqual(messages[0].detail.images[2].url_list,[])
})
test('streamed records keep work matching and normalize video source objects', () => {
  const unrelated={awemeId:'456',images:[{uri:'unrelated',urlList:['https://cdn.example/wrong.webp']}]}
  const video={awemeId:'123',authorInfo:{nickname:'作者'},video:{playAddr:[{src:'https://cdn.example/right.mp4'}]}}
  const {messages}=setup({location:{href:'https://www.douyin.com/video/123',pathname:'/video/123'},__pace_f:[[1,'4:'+JSON.stringify(unrelated)+'\n5:'+JSON.stringify(video)+'\n']]})
  assert.equal(messages.length,1)
  assert.equal(messages[0].detail.aweme_id,'123')
  assert.deepEqual(messages[0].detail.video.play_addr.url_list,['https://cdn.example/right.mp4'])
  assert.equal(messages[0].detail.images,undefined)
})

test('an incomplete initial work cannot pin the parser before complete streamed data arrives', () => {
  const {context,messages}=setup({__INITIAL_STATE__:{aweme_id:'123',video:{}}})
  assert.equal(context.__shiyingRead(),null)
  assert.equal(messages.length,0)
  context.__pace_f=[[1,'1:'+JSON.stringify(note)+'\n']]
  assert.equal(context.__shiyingRead().images.length,3)
  assert.equal(messages.length,1)
})

test('only visible explicit authentication gates report blocked; optional login prompts do not', () => {
  const elements=[]
  const {context}=setup({document:{getElementById:()=>null,querySelectorAll:()=>elements},getComputedStyle:element=>element.style})
  const dialog=(innerText,visible=true)=>({innerText,getClientRects:()=>visible?[{}]:[],style:{display:'block',visibility:'visible'}})
  elements.push(dialog('登录，发现更多精彩'),dialog('安全验证',false))
  assert.equal(context.__shiyingBlockReason(),'')
  elements.push(dialog('请先登录后继续观看'))
  assert.equal(context.__shiyingBlockReason(),'login')
  elements.unshift(dialog('安全验证：拖动滑块'))
  assert.equal(context.__shiyingBlockReason(),'verification')
})

test('video data after a byte-counted text record is read without treating text as work data', () => {
  const video={awemeId:'123',video:{playAddr:[{src:'https://cdn.example/right.mp4'}]}}
  const text='中文🙂\n2:'+JSON.stringify({...video,video:{playAddr:[{src:'https://cdn.example/wrong.mp4'}]}})
  const stream='8:T'+new TextEncoder().encode(text).length.toString(16)+','+text+'2:'+JSON.stringify(video)+'\n'
  const {messages}=setup({location:{href:'https://www.douyin.com/video/123',pathname:'/video/123'},__pace_f:[[1,stream.slice(0,40)],[1,stream.slice(40)]]})
  assert.equal(messages.length,1)
  assert.deepEqual(messages[0].detail.video.play_addr.url_list,['https://cdn.example/right.mp4'])
})

test('mobile share loader data returns only the requested video', () => {
  const detail={aweme_id:'123',desc:'视频文案',author:{nickname:'作者'},video:{play_addr:{url_list:['https://cdn.example/mobile.mp4']}}}
  const {messages}=setup({location:{href:'https://www.iesdouyin.com/share/video/123/?from_ssr=1',pathname:'/share/video/123/'},_ROUTER_DATA:{loaderData:{'video_(id)/page':{videoInfoRes:{item_list:[{...detail,aweme_id:'456'},detail],status_code:0}}}}})
  assert.equal(messages.length,1)
  assert.equal(messages[0].detail.aweme_id,'123')
  assert.deepEqual(messages[0].detail.video.play_addr.url_list,['https://cdn.example/mobile.mp4'])
})

test('retains alternate playback sources without adding download or suffix-logo addresses', () => {
  const detail={aweme_id:'123',video:{
    play_addr:{url_list:['https://aweme.snssdk.com/aweme/v1/playwm/?video_id=example']},
    play_addr_h264:{url_list:['https://cdn.example/h264.mp4']},
    bit_rate:[{play_addr:{url_list:['https://cdn.example/quality.mp4']}}],
    download_addr:{url_list:['https://cdn.example/download.mp4']},
    download_suffix_logo_addr:{url_list:['https://cdn.example/suffix.mp4']},
  }}
  const {messages}=setup({location:{href:'https://www.douyin.com/video/123',pathname:'/video/123'},__INITIAL_STATE__:detail})
  assert.deepEqual(messages[0].detail.video.play_addr.url_list,[
    'https://cdn.example/h264.mp4','https://cdn.example/quality.mp4','https://aweme.snssdk.com/aweme/v1/playwm/?video_id=example',
  ])
})
