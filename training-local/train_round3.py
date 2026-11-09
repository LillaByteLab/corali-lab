"""Continue LoRA training for validated local operation selection, caching only the immutable prefix of the network.

Cache tensors contain synthetic training data only. Validation and test are never
loaded here. The cached path is compared to ordinary HF loss and gradients first.
"""
import os
os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
import argparse, gc, hashlib, json, math, random, time
from pathlib import Path
import torch
import psutil
from transformers import AutoTokenizer, AutoModelForCausalLM
from transformers.masking_utils import create_causal_mask
from peft import LoraConfig, get_peft_model, PeftModel
from cpu_low_memory import install

parser = argparse.ArgumentParser()
parser.add_argument('--pilot', action='store_true')
parser.add_argument('--experiment',choices=['round3','round3b'],default='round3')
args = parser.parse_args()
root = Path(__file__).resolve().parent
data = root / args.experiment
out = data / ('pilot' if args.pilot else 'run')
if out.exists():
    raise SystemExit('Output already exists; preserve the previous run.')
out.mkdir()
cache_dir = out / 'prefix-cache'; cache_dir.mkdir()
base = root.parent / '.tooling/training-model'
torch.set_num_threads(6); torch.manual_seed(32804)
psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
started = time.monotonic()

def log(event, **extra):
    row = {'event': event, 'time': time.time(), 'elapsedSeconds': round(time.monotonic()-started, 2),
           'availableGiB': round(psutil.virtual_memory().available/2**30, 2),
           'rssGiB': round(psutil.Process().memory_info().rss/2**30, 2), **extra}
    with (out / 'events.jsonl').open('a', encoding='utf8') as f:
        f.write(json.dumps(row) + '\n')
    print(json.dumps(row), flush=True)

def guard():
    if psutil.virtual_memory().available < 600*1024**2:
        raise RuntimeError('Less than 600 MiB available RAM; stop and preserve state.')

manifest = json.loads((data/'manifest.json').read_text())
assert hashlib.sha256((data/'train.jsonl').read_bytes()).hexdigest() == manifest['splits']['train']['sha256']
records = [json.loads(line) for line in (data/'train.jsonl').read_text(encoding='utf8').splitlines()]
if args.pilot:
    records = records[:2]
log('loading', trainingExamples=len(records))
tokenizer = AutoTokenizer.from_pretrained(base, local_files_only=True, trust_remote_code=False)
model = AutoModelForCausalLM.from_pretrained(base, local_files_only=True, trust_remote_code=False,
    torch_dtype=torch.bfloat16, low_cpu_mem_usage=True, attn_implementation='eager')
model.config.use_cache = False
install(model)
config = LoraConfig(r=8, lora_alpha=16, lora_dropout=0, target_modules=['q_proj','k_proj','v_proj','o_proj'],
                    layers_to_transform=[24,25,26,27], bias='none', task_type='CAUSAL_LM')
model = PeftModel.from_pretrained(model, root / manifest['plannedTraining']['resumeAdapter'], is_trainable=True, local_files_only=True)
network = model.base_model.model.model
head = model.base_model.model.lm_head
parameters = [p for p in model.parameters() if p.requires_grad]
assert sum(p.numel() for p in parameters) == 311296
assert all(not p.requires_grad for layer in network.layers[:24] for p in layer.parameters())
log('loaded', trainableParameters=sum(p.numel() for p in parameters))

def tokenize(record):
    prefix = tokenizer.apply_chat_template(record['messages'][:-1], tokenize=True, add_generation_prompt=True)
    ids = tokenizer.apply_chat_template(record['messages'], tokenize=True, add_generation_prompt=False)
    assert ids[:len(prefix)] == prefix and len(prefix) < len(ids) <= 512
    return torch.tensor([ids]), len(prefix)

def kwargs_for(embeddings):
    positions = torch.arange(embeddings.shape[1])
    position_ids = positions.unsqueeze(0)
    mask = create_causal_mask(config=network.config, input_embeds=embeddings,
                             attention_mask=torch.ones(embeddings.shape[:2], dtype=torch.long),
                             cache_position=positions, past_key_values=None, position_ids=position_ids)
    return {'attention_mask': mask, 'position_ids': position_ids, 'cache_position': positions,
            'position_embeddings': network.rotary_emb(embeddings, position_ids), 'use_cache': False}

def make_cache(record):
    ids, prefix = tokenize(record)
    with torch.no_grad():
        hidden = network.embed_tokens(ids)
        kwargs = kwargs_for(hidden)
        for layer in network.layers[:24]:
            hidden = layer(hidden, **kwargs)
    return {'hidden': hidden.detach(), 'ids': ids, 'prefix': prefix, 'kwargs': kwargs}

def cached_loss(cached, numeric_weight=1.0):
    hidden = cached['hidden']
    for layer in network.layers[24:]:
        hidden = layer(hidden, **cached['kwargs'])
    hidden = network.norm(hidden)
    # Only answer positions need the large vocabulary projection. The predictor
    # of the first answer token is the last prompt token (causal one-token shift).
    logits = head(hidden[:, cached['prefix']-1:-1, :]).float()
    target = cached['ids'][:, cached['prefix']:]
    losses = torch.nn.functional.cross_entropy(logits.reshape(-1, logits.shape[-1]), target.reshape(-1), reduction='none')
    weights = torch.ones_like(losses)
    if numeric_weight != 1.0:
        for i, token in enumerate(target.reshape(-1).tolist()):
            if tokenizer.decode([token]).strip().isdigit(): weights[i] = numeric_weight
    return (losses*weights).sum()/weights.sum()

def fingerprint():
    h = hashlib.sha256()
    for p in parameters:
        h.update(p.detach().float().numpy().tobytes())
    return h.hexdigest()

steps = 0
optimizer = None
try:
    # Compare ordinary full forward/backward to cached-prefix + answer-only head.
    model.eval()
    example = make_cache(records[0])
    ids = example['ids']; labels = ids.clone(); labels[:, :example['prefix']] = -100
    reference = model(input_ids=ids, attention_mask=torch.ones_like(ids), labels=labels).loss
    reference.backward()
    grads = [p.grad.detach().clone() for p in parameters]
    ref_value = reference.detach().float(); del reference
    model.zero_grad(set_to_none=True)
    optimized = cached_loss(example); optimized.backward()
    torch.testing.assert_close(optimized.detach().float(), ref_value, rtol=2e-4, atol=2e-4)
    max_error = max(float((p.grad - g).abs().max()) for p, g in zip(parameters, grads))
    for p, g in zip(parameters, grads):
        torch.testing.assert_close(p.grad, g, rtol=0.02, atol=2e-4)
    log('equivalence_verified', loss=float(ref_value), optimizedLoss=float(optimized.detach()), maxGradientError=max_error)
    del example, ids, labels, grads, optimized, ref_value
    model.zero_grad(set_to_none=True); gc.collect()
    for index, record in enumerate(records):
        t = time.monotonic()
        if record.get('cacheSource'):
            source=(root/record['cacheSource']).resolve()
            assert source.is_relative_to((root/'round3/run/prefix-cache').resolve())
            cached=torch.load(source,weights_only=True)
            expected_ids,expected_prefix=tokenize(record)
            assert torch.equal(cached['ids'],expected_ids) and cached['prefix']==expected_prefix
        else:
            cached = make_cache(record)
        torch.save(cached, cache_dir/(record['id']+'.pt'))
        log('cached', index=index+1, total=len(records), tokens=cached['ids'].shape[1], reused=bool(record.get('cacheSource')), seconds=round(time.monotonic()-t,2))
        del cached
        guard()
    # Free immutable decoder weights after all training-only prefix computations.
    # Original indices stay intact so adapter keys and exported GGUF remain valid.
    for i in range(24):
        network.layers[i] = torch.nn.Identity()
    network.embed_tokens = torch.nn.Identity()  # head keeps the shared output weights
    gc.collect()
    # Keep the fixed output projection in FP32 once instead of allocating and
    # converting its 151936x1536 weights on every forward and backward pass.
    head.weight = torch.nn.Parameter(head.weight.detach().float(), requires_grad=False)
    if os.name == 'nt':
        import ctypes
        current_process=ctypes.windll.kernel32.GetCurrentProcess
        current_process.restype=ctypes.c_void_p
        trim=ctypes.windll.psapi.EmptyWorkingSet
        trim.argtypes=[ctypes.c_void_p];trim.restype=ctypes.c_int
        log('working_set_trim', succeeded=bool(trim(current_process())))
    log('frozen_prefix_released')
    base_lr = manifest['plannedTraining']['learningRate']
    optimizer = torch.optim.AdamW(parameters, lr=base_lr)
    before = fingerprint()
    epochs = 1 if args.pilot else manifest['plannedTraining']['epochs']
    total_steps = epochs*len(records)
    warmup = max(1, int(total_steps*0.05))
    model.train()
    for epoch in range(epochs):
        order = list(records); random.Random(32805+epoch).shuffle(order)
        losses = []
        for record in order:
            t = time.monotonic()
            progress = max(0, steps-warmup)/max(1,total_steps-warmup)
            lr = base_lr * (min(1, (steps+1)/warmup) if steps < warmup else (0.1+0.9*0.5*(1+math.cos(math.pi*progress))))
            for group in optimizer.param_groups: group['lr'] = lr
            optimizer.zero_grad(set_to_none=True)
            cached = torch.load(cache_dir/(record['id']+'.pt'), weights_only=True)
            loss = cached_loss(cached)
            assert torch.isfinite(loss), 'Non-finite loss'
            loss.backward(); torch.nn.utils.clip_grad_norm_(parameters, 1.0); optimizer.step()
            steps += 1; losses.append(float(loss.detach()))
            log('step', step=steps, total=total_steps, epoch=epoch+1, example=record['id'],
                loss=losses[-1], lr=lr, seconds=round(time.monotonic()-t,2))
            del cached, loss
            if steps % 40 == 0:
                checkpoint = out / ('checkpoint-'+str(steps))
                model.save_pretrained(checkpoint, safe_serialization=True)
                torch.save(optimizer.state_dict(), checkpoint/'optimizer.pt')
            guard()
        checkpoint = out/('epoch-'+str(epoch+1))
        model.save_pretrained(checkpoint, safe_serialization=True)
        torch.save(optimizer.state_dict(), checkpoint/'optimizer.pt')
        log('epoch_completed', epoch=epoch+1, meanLoss=sum(losses)/len(losses), adapter=str(checkpoint))
    after = fingerprint(); assert after != before
    result = {'status': 'pilot_verified' if args.pilot else 'trained_unvalidated', 'optimizerSteps': steps,
              'trainableParameters': 311296, 'beforeSha256': before, 'afterSha256': after,
              'weightsChanged': True, 'seconds': round(time.monotonic()-started,2),
              'objective': 'local_operation_routing', 'threads': 6, 'continuedFrom': manifest['plannedTraining']['resumeAdapter'], 'optimizerResetForNewObjective': True,
              'validationOrTestReadForTraining': False, 'baseWeightsModified': False, 'releaseAllowed': False}
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    log('completed', **result)
except Exception as exc:
    model.save_pretrained(out/'partial-adapter', safe_serialization=True)
    if optimizer is not None: torch.save(optimizer.state_dict(),out/'partial-adapter/optimizer.pt')
    log('failed', message=str(exc), optimizerSteps=steps)
    raise
