export function imtProjectDirectories(files: File[]) {
  const groups = new Map<string, File[]>()
  const roots = new Set<string>()
  for (const file of files) {
    const parts = file.webkitRelativePath.split('/')
    if (parts.length < 2) throw Error('请选择完整的工程目录')
    roots.add(parts[0])
    const path = parts.slice(1, -1).join('/')
    const group = groups.get(path) ?? []
    group.push(file)
    groups.set(path, group)
  }
  const projects = [...groups].filter(([, group]) =>
    group.some((file) => file.name === 'manifest.json'),
  )
  const sides = ['baseline', 'dynamic']
  const topDirectories = new Set(
    [...groups.keys()].map((path) => path.split('/')[0]),
  )
  if (roots.size === 1) {
    if (!sides.some((side) => topDirectories.has(side))) {
      if (projects.length === 1 && projects[0][0] === '') return projects
    } else {
      const missing: string[] = []
      for (const side of sides) {
        if (!topDirectories.has(side)) missing.push(side + ' 子目录缺失或为空')
        else if (!projects.some(([path]) => path === side))
          missing.push('缺少 ' + side + '/manifest.json')
      }
      if (missing.length)
        throw Error('OTA 工程目录不完整：' + missing.join('；'))
      if (projects.every(([path]) => sides.includes(path)))
        return projects.sort(([a], [b]) => a.localeCompare(b))
    }
  }
  throw Error(
    '请选择含 manifest.json 的工程目录，或含 baseline、dynamic 子目录的 OTA 总目录。',
  )
}
