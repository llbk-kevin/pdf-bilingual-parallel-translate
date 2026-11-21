"""Share large path-only leaf Forms across the two ordinary page grafts."""
from collections import Counter
from uuid import uuid4
from hashlib import sha256

from pypdf.generic import ContentStream, DictionaryObject, NameObject

MIN_BYTES = 128 * 1024
IDENTITY = (1, 0, 0, 1, 0, 0)
FORM_KEYS = {'/Type','/Subtype','/FormType','/BBox','/Matrix','/Resources',
             '/Filter','/DecodeParms','/Length'}
PATH_OPS = set(b'q Q cm m l c v y h re S s f F f* B B* b b* n W W* w J j M d g G rg RG k K'.split())


def leaf_reason(obj, reader):
    if set(obj) - FORM_KEYS or '/Resources' not in obj:
        return 'form_dictionary'
    if set(obj['/Resources']) - {'/ProcSet'}:
        return 'resource_dependencies'
    if any(op not in PATH_OPS for _, op in ContentStream(obj, reader).operations):
        return 'non_path_operators'
    return None


def calls(stream, pdf):
    """Collect actual Do instructions and their inherited graphics state.

    Only accept simple path painting and isolated graphics-state changes before
    a call. Unmodelled clips, text/graphics interactions and effects taint
    that scope until its matching Q. Unknown contexts cannot match.
    """
    state = {'matrix': (), 'stroke': (b'G',0), 'fill': (b'g',0)}
    stack = []
    result = []
    for args, op in ContentStream(stream, pdf).operations:
        if op == b'q':
            stack.append(state.copy())
        elif op == b'Q':
            if not stack:
                raise ValueError('unbalanced graphics state')
            state = stack.pop()
        elif op == b'Do':
            result.append((args[0], state.copy()))
        elif op == b'cm':
            matrix = tuple(args)
            if matrix != IDENTITY:
                state['matrix'] += (matrix,)
        elif op in (b'g',b'rg',b'k',b'G',b'RG',b'K'):
            state['fill' if op.islower() else 'stroke'] = (op,*args)
        elif op in (b'w',b'J',b'j',b'M',b'd'):
            state[op] = tuple(args)
        elif op not in (b'm',b'l',b'c',b'v',b'y',b'h',b're',b'n',b'S',b's',
                        b'f',b'F',b'f*',b'B',b'B*',b'b',b'b*'):
            state['unknown'] = True
    return result


def target(parent, name):
    return parent['/Resources']['/XObject'][name]


def binding(parent, name, ref):
    # Keep shared resource dictionaries private at the point of mutation.
    resources = DictionaryObject(parent['/Resources'])
    objects = DictionaryObject(resources['/XObject'])
    objects[name] = ref
    resources[NameObject('/XObject')] = objects
    parent[NameObject('/Resources')] = resources


def indirect_edges(obj):
    from pypdf.generic import IndirectObject
    pending = [obj]
    while pending:
        value = pending.pop()
        if isinstance(value, IndirectObject):
            yield value.idnum
        elif isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)


def prune_detached(writer, seeds):
    # pypdf's usual one-pass orphan check can retain descendants of a
    # detached caller. Follow only edges released by our own replacements.
    incoming = Counter(edge for obj in writer._objects for edge in indirect_edges(obj))
    pending = list(seeds)
    while pending:
        num = pending.pop()
        obj = writer._objects[num-1]
        if incoming[num] or obj is None:
            continue
        writer._objects[num-1] = None
        for edge in indirect_edges(obj):
            incoming[edge] -= 1
            if not incoming[edge]:
                pending.append(edge)


class VectorSharing:
    def __init__(self):
        self.key = 'BilingualVector' + uuid4().hex
        self.checked = {}
        self.eligible = {}
        self.pages = {}
        self.skips = Counter()
        self.records = []
        self.detached = set()

    def mark(self, src, reader, page, number):
        if page.rotation or page.cropbox != page.mediabox:
            return
        found = set()
        source_page = reader.pages[number-1]
        if '/Group' in source_page:
            return
        resources = source_page['/Resources'] if '/Resources' in source_page else {}
        colors = resources.get('/ColorSpace')
        if colors and any(str(k).startswith('/Default') for k in colors.get_object()):
            return
        objects = resources.get('/XObject')
        for ref in objects.get_object().values() if objects else ():
            obj = ref.get_object()
            if not hasattr(ref, 'idnum') or obj.get('/Subtype') != '/Form':
                continue
            x = ref.idnum
            if x not in self.checked:
                eligible = False
                if len(obj._data) >= MIN_BYTES:
                    reason = leaf_reason(obj, reader)
                    if reason:
                        self.skips[reason] += 1
                    else:
                        eligible = True
                        self.eligible[x] = sha256(obj.get_data()).digest()
                        src.xref_set_key(x, self.key, str(x))
                self.checked[x] = eligible
            if self.checked[x]:
                found.add(x)
        if found:
            self.pages[number] = found

    def pane(self, page, name, pdf):
        wrapper = target(page, name)
        if set(wrapper) - FORM_KEYS or '/Resources' not in wrapper:
            return None
        operations = ContentStream(wrapper, pdf).operations
        if len(operations) != 1 or operations[0][1] != b'Do':
            return None
        inner_name = operations[0][0][0]
        inner = target(wrapper, inner_name)
        if set(inner) - FORM_KEYS or tuple(inner.get('/Matrix', IDENTITY)) != IDENTITY:
            return None
        entries = []
        for alias, context in calls(inner, pdf):
            obj = target(inner, alias)
            origin = obj.get('/'+self.key)
            if origin is not None:
                entries.append((alias, int(origin), context, obj))
        return wrapper, inner_name, inner, entries

    def link_page(self, page, number, writer):
        top = calls(page.get_contents(), writer)
        if len(top) != 2 or top[0][1] != top[1][1] or 'unknown' in top[0][1]:
            return
        left = self.pane(page, top[0][0], writer)
        right = self.pane(page, top[1][0], writer)
        if not left or not right:
            return
        width = float(page.mediabox.width)/2
        if (tuple(left[0].get('/Matrix', IDENTITY)) != IDENTITY or
                tuple(right[0].get('/Matrix', IDENTITY)) != (1,0,0,1,width,0) or
                left[0]['/BBox'] != right[0]['/BBox'] or left[2]['/BBox'] != right[2]['/BBox']):
            return
        if [e[1] for e in left[3]] != [e[1] for e in right[3]]:
            return
        # Copy the two small caller streams only when a binding changes. This
        # also isolates multiple uses of the same parent across different pages.
        from copy import copy
        wrapper, inner = copy(right[0]), copy(right[2])
        accepted = []
        rejected = set()
        for (ln, origin, lc, original), (rn, _, rc, rewritten) in zip(left[3], right[3]):
            if (origin not in self.pages[number] or 'unknown' in lc or lc != rc or
                    sha256(original.get_data()).digest() != self.eligible[origin] or
                    any(original.get(k) != rewritten.get(k) for k in ('/BBox','/Matrix','/FormType'))):
                rejected.add(rn)
                continue
            accepted.append((ln, rn, origin, original))
        paths = []
        for ln, rn, origin, original in accepted:
            if rn in rejected:
                continue
            binding(inner, rn, original.indirect_reference)
            paths.append({'source_page': number, 'source_object': origin,
                          'left_path': [top[0][0],left[1],ln],
                          'right_path': [top[1][0],right[1],rn]})
        if paths:
            # _add_object returns an existing ref if the copy still owns one.
            inner.indirect_reference = wrapper.indirect_reference = None
            binding(wrapper, right[1], writer._add_object(inner))
            self.detached.add(right[0].indirect_reference.idnum)
            for sub in (page.raw_get('/Resources'), page['/Resources'].raw_get('/XObject')):
                if hasattr(sub, 'idnum'):
                    self.detached.add(sub.idnum)
            binding(page, top[1][0], writer._add_object(wrapper))
            self.records.extend(paths)

    def apply(self, writer, selected):
        for i, number in enumerate(selected):
            if number in self.pages:
                before = len(self.records)
                self.link_page(writer.pages[i], number, writer)
                used = {r['source_object'] for r in self.records[before:]}
                self.skips['unverified_call_site'] += len(self.pages[number] - used)
        if self.detached:
            prune_detached(writer, self.detached)
        if self.eligible:
            for obj in writer._objects:
                if isinstance(obj, dict):
                    obj.pop('/'+self.key, None)

    def report(self, path, selected):
        from pypdf import PdfReader
        sizes = {}
        if self.records:
            with PdfReader(path) as pdf:
                for row in self.records:
                    page = pdf.pages[selected.index(row['source_page'])]
                    refs = []
                    for side in ('left_path','right_path'):
                        obj = page
                        for name in row[side]:
                            stream = obj.get_contents() if obj is page else obj
                            if not any(alias == name for alias, _ in calls(stream, pdf)):
                                raise ValueError('Shared Form is present but not painted')
                            obj = target(obj, name)
                        refs.append(obj.indirect_reference.idnum)
                    if refs[0] != refs[1]:
                        raise ValueError('Vector sharing lost during final PDF serialization')
                    row['final_object'] = refs[0]
                    sizes[refs[0]] = len(obj._data)
        return {'eligible_sources':len(self.eligible),'shared_objects':len(sizes),
                'shared_encoded_bytes':sum(sizes.values()),'skipped':dict(+self.skips),
                'paint_paths':self.records}
